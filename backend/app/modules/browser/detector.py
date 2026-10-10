"""Form detection (CONTRACTS.md section 12).

Two interchangeable front-ends produce the *same* intermediate payload, which a single
shared ``_finalize`` turns into a :class:`DetectedForm`:

* :func:`detect_form` runs one ``page.evaluate`` in the live Chromium page;
* :func:`detect_form_from_html` walks the HTML with ``html.parser`` only, so the rules
  (and the mapper on top of them) stay unit-testable without a browser.

Keeping the browser-side script limited to *structural extraction* -- and the field-type
mapping, required-flag rules, radio grouping and blocker classification in Python -- is
what keeps both paths behaviourally aligned.

Blockers are never worked around. CAPTCHA, OTP/2FA, login walls and forced account
registration are reported so the caller can pause and hand control back to the human.
"""
from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from typing import Any, Iterator

from app.models.enums import FieldType, PauseReason
from app.modules.browser.schemas import Blocker, DetectedField, DetectedForm, FieldOption

logger = logging.getLogger(__name__)

# input types that are never user-answerable form questions
SKIP_INPUT_TYPES = {"hidden", "submit", "button", "reset", "image"}
# containers whose controls are site chrome (search boxes, newsletter signup), not the form
CHROME_TAGS = {"nav", "header", "footer"}
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
HEADING_TAGS = ("h1", "h2", "h3", "h4")

_TYPE_MAP: dict[str, FieldType] = {
    "": FieldType.TEXT,
    "text": FieldType.TEXT,
    "search": FieldType.TEXT,
    "password": FieldType.TEXT,
    "email": FieldType.EMAIL,
    "tel": FieldType.PHONE,
    "number": FieldType.NUMBER,
    "range": FieldType.NUMBER,
    "url": FieldType.URL,
    "file": FieldType.FILE,
    "date": FieldType.DATE,
    "datetime-local": FieldType.DATE,
    "month": FieldType.DATE,
    "week": FieldType.DATE,
    "time": FieldType.DATE,
    "checkbox": FieldType.CHECKBOX,
    "radio": FieldType.RADIO,
    "hidden": FieldType.HIDDEN,
}

OTP_RE = re.compile(r"\botp\b|one[\s_-]?time[\s_-]?(?:code|password|pin)|verification code|2fa|two[\s_-]?factor|authenticator code", re.I)
CAPTCHA_TOKENS = ("recaptcha", "hcaptcha", "turnstile", "captcha")
LOGIN_TEXT_RE = re.compile(r"\bsign in\b|\blog ?in\b|\bsignin\b", re.I)
REGISTER_TEXT_RE = re.compile(r"create an? account|create account|\bregister\b|sign ?up", re.I)
CONFIRM_PASSWORD_RE = re.compile(r"confirm|re-?enter|re-?type|repeat", re.I)
APPLICATION_FIELD_RE = re.compile(
    r"resume|\bcv\b|cover[\s_-]*letter|linkedin|github|portfolio|notice[\s_-]*period|ctc|salary"
    r"|experience|first[\s_-]*name|last[\s_-]*name|full[\s_-]*name|phone|mobile|apply|application|why",
    re.I,
)

# --------------------------------------------------------------------------- browser side

#: Structural extraction executed in the page. Returns the raw payload consumed by
#: :func:`_finalize`. Mirrors :class:`_HtmlExtractor` below - change both together.
EXTRACT_JS = r"""
() => {
  const SKIP_TYPES = new Set(['hidden', 'submit', 'button', 'reset', 'image']);
  const CHROME = new Set(['NAV', 'HEADER', 'FOOTER']);
  const HEADINGS = 'h1,h2,h3,h4';
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const textOf = (el) => clean(el ? (el.innerText || el.textContent || '') : '');
  const attr = (el, a) => { const v = el.getAttribute(a); return v === null ? null : v; };
  const simpleId = (s) => /^[A-Za-z][A-Za-z0-9_-]*$/.test(s || '');

  const labelsFor = new Map();
  document.querySelectorAll('label[for]').forEach((l) => {
    const key = l.getAttribute('for');
    if (key && !labelsFor.has(key)) labelsFor.set(key, l);
  });

  const pathSelector = (el) => {
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1) {
      const tag = node.tagName.toLowerCase();
      if (tag === 'body' || tag === 'html') break;
      const parent = node.parentElement;
      let idx = 1;
      if (parent) {
        const sibs = Array.prototype.filter.call(parent.children, (c) => c.tagName === node.tagName);
        idx = sibs.indexOf(node) + 1;
      }
      parts.unshift(tag + ':nth-of-type(' + idx + ')');
      node = parent;
    }
    return parts.join(' > ');
  };

  const uniqueSelector = (el) => {
    const id = attr(el, 'id');
    if (id && simpleId(id) && document.querySelectorAll('#' + id).length === 1) return '#' + id;
    const tag = el.tagName.toLowerCase();
    const name = attr(el, 'name');
    if (name && document.querySelectorAll(tag + '[name="' + name + '"]').length === 1) {
      return tag + '[name="' + name + '"]';
    }
    const type = attr(el, 'type');
    if (type && document.querySelectorAll(tag + '[type="' + type + '"]').length === 1) {
      return tag + '[type="' + type + '"]';
    }
    return pathSelector(el);
  };

  const isHidden = (el) => {
    if (el.hasAttribute('hidden')) return true;
    const style = (attr(el, 'style') || '').replace(/\s+/g, '').toLowerCase();
    if (style.indexOf('display:none') >= 0 || style.indexOf('visibility:hidden') >= 0) return true;
    return false;
  };

  const inChrome = (el) => {
    let node = el.parentElement;
    while (node) { if (CHROME.has(node.tagName)) return true; node = node.parentElement; }
    return false;
  };

  const precedingText = (el) => {
    let sib = el.previousElementSibling;
    let hops = 0;
    while (sib && hops < 3) {
      const t = textOf(sib);
      if (t) return t;
      sib = sib.previousElementSibling;
      hops += 1;
    }
    const parent = el.parentElement;
    if (parent) {
      let own = '';
      Array.prototype.forEach.call(parent.childNodes, (n) => { if (n.nodeType === 3) own += ' ' + n.nodeValue; });
      if (clean(own)) return clean(own);
    }
    return null;
  };

  const ownLabel = (el) => {
    const id = attr(el, 'id');
    if (id && labelsFor.has(id)) return { text: textOf(labelsFor.get(id)), source: 'label[for]' };
    const aria = attr(el, 'aria-label');
    if (clean(aria)) return { text: clean(aria), source: 'aria-label' };
    const by = attr(el, 'aria-labelledby');
    if (by) {
      const parts = by.split(/\s+/).map((r) => { const t = document.getElementById(r); return t ? textOf(t) : ''; });
      const joined = clean(parts.join(' '));
      if (joined) return { text: joined, source: 'aria-labelledby' };
    }
    const wrap = el.closest('label');
    if (wrap) { const t = textOf(wrap); if (t) return { text: t, source: 'wrapping-label' }; }
    const ph = attr(el, 'placeholder');
    if (clean(ph)) return { text: clean(ph), source: 'placeholder' };
    const prev = precedingText(el);
    if (prev) return { text: prev, source: 'preceding-text' };
    const nm = attr(el, 'name');
    if (nm) return { text: nm, source: 'name' };
    return { text: null, source: 'none' };
  };

  const groupLabel = (el) => {
    const fs = el.closest('fieldset');
    if (fs) { const lg = fs.querySelector('legend'); if (lg) return textOf(lg); }
    const box = el.closest('.field, .form-field, .form-group, [data-field]');
    if (box) {
      const lab = box.querySelector('label, legend, .label');
      if (lab && !lab.contains(el)) return textOf(lab);
    }
    return precedingText(el.parentElement || el);
  };

  const sectionOf = (el) => {
    let node = el.parentElement;
    while (node && node.tagName !== 'BODY' && node.tagName !== 'HTML') {
      if (node.tagName === 'FIELDSET') {
        const lg = node.querySelector('legend');
        if (lg && !lg.contains(el)) return textOf(lg);
      }
      const h = node.querySelector(HEADINGS);
      if (h && !h.contains(el)) return textOf(h);
      node = node.parentElement;
    }
    return null;
  };

  const fields = [];
  document.querySelectorAll('input, select, textarea').forEach((el) => {
    const tag = el.tagName.toLowerCase();
    const type = (attr(el, 'type') || '').toLowerCase();
    if (tag === 'input' && SKIP_TYPES.has(type)) return;
    if (isHidden(el) || inChrome(el)) return;
    const lab = ownLabel(el);
    const options = [];
    if (tag === 'select') {
      Array.prototype.forEach.call(el.querySelectorAll('option'), (o) => {
        options.push({ value: o.getAttribute('value') === null ? textOf(o) : o.getAttribute('value'), label: textOf(o), selector: null });
      });
    }
    fields.push({
      tag: tag,
      type: type,
      name: attr(el, 'name'),
      id: attr(el, 'id'),
      placeholder: attr(el, 'placeholder'),
      autocomplete: attr(el, 'autocomplete'),
      required: el.hasAttribute('required') || (attr(el, 'aria-required') || '').toLowerCase() === 'true',
      disabled: el.hasAttribute('disabled'),
      label: lab.text,
      label_source: lab.source,
      group_label: type === 'radio' ? groupLabel(el) : null,
      value: attr(el, 'value'),
      options: options,
      selector: uniqueSelector(el),
      section: sectionOf(el),
    });
  });

  // submit control
  let submit = null;
  const byType = document.querySelector('button[type="submit"], input[type="submit"]');
  if (byType) {
    submit = uniqueSelector(byType);
  } else {
    const btns = Array.prototype.slice.call(document.querySelectorAll('button, input[type="button"], a.button'));
    const hit = btns.filter((b) => /submit|apply|send application/i.test(textOf(b) || attr(b, 'value') || ''))[0];
    if (hit) submit = uniqueSelector(hit);
  }

  // captcha widgets (detected, never solved)
  const captcha = [];
  const push = (sel, detail) => { if (!captcha.some((c) => c.selector === sel)) captcha.push({ selector: sel, detail: detail }); };
  ['.g-recaptcha', '.h-captcha', '.cf-turnstile', '[data-sitekey]', '#captcha', '.captcha'].forEach((sel) => {
    if (document.querySelector(sel)) push(sel, sel);
  });
  Array.prototype.forEach.call(document.querySelectorAll('iframe'), (f) => {
    const src = (attr(f, 'src') || '').toLowerCase();
    ['recaptcha', 'hcaptcha', 'turnstile', 'captcha'].forEach((tok) => {
      if (src.indexOf(tok) >= 0) push('iframe[src*="' + tok + '"]', src.slice(0, 200));
    });
  });

  const headings = [];
  Array.prototype.forEach.call(document.querySelectorAll('h1,h2,h3'), (h) => { const t = textOf(h); if (t) headings.push(t); });

  return {
    url: document.location ? document.location.href : '',
    title: clean(document.title),
    fields: fields,
    submit_selector: submit,
    captcha: captcha,
    headings: headings,
    text_sample: clean(document.body ? (document.body.innerText || document.body.textContent || '') : '').slice(0, 6000),
  };
}
"""


def detect_form(page: Any) -> DetectedForm:
    """Detect the application form on a live Playwright page."""
    raw = page.evaluate(EXTRACT_JS)
    if not raw.get("url"):
        raw["url"] = getattr(page, "url", "") or ""
    form = _finalize(raw)
    logger.info(
        "Detected %d field(s), submit=%s, blockers=%s at %s",
        len(form.fields),
        form.submit_selector,
        [b.kind.value for b in form.blockers],
        form.url,
    )
    return form


# --------------------------------------------------------------------------- html side


class _Node:
    """Minimal DOM node (elements + text) built by :class:`_DomParser`."""

    __slots__ = ("tag", "attrs", "parent", "nodes")

    def __init__(self, tag: str, attrs: dict[str, str], parent: "_Node | None" = None) -> None:
        self.tag = tag
        self.attrs = attrs
        self.parent = parent
        self.nodes: list[Any] = []

    # -- structure
    @property
    def children(self) -> list["_Node"]:
        return [n for n in self.nodes if isinstance(n, _Node)]

    def descendants(self) -> Iterator["_Node"]:
        for child in self.children:
            yield child
            yield from child.descendants()

    def ancestors(self) -> Iterator["_Node"]:
        node = self.parent
        while node is not None:
            yield node
            node = node.parent

    def closest(self, *tags: str) -> "_Node | None":
        for node in self.ancestors():
            if node.tag in tags:
                return node
        return None

    def contains(self, other: "_Node") -> bool:
        return other is self or any(a is self for a in other.ancestors())

    # -- content
    def get(self, name: str) -> str | None:
        return self.attrs.get(name)

    def has(self, name: str) -> bool:
        return name in self.attrs

    def classes(self) -> list[str]:
        return (self.attrs.get("class") or "").split()

    def text(self) -> str:
        parts: list[str] = []
        for node in self.nodes:
            if isinstance(node, str):
                parts.append(node)
            elif node.tag not in ("script", "style"):
                parts.append(node.text())
        return _clean(" ".join(parts))

    def own_text(self) -> str:
        return _clean(" ".join(n for n in self.nodes if isinstance(n, str)))

    def previous_siblings(self) -> list["_Node"]:
        if self.parent is None:
            return []
        sibs = self.parent.children
        idx = sibs.index(self)
        return sibs[:idx][::-1]


class _DomParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#document", {})
        self._stack: list[_Node] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag, {k.lower(): (v if v is not None else "") for k, v in attrs}, self._stack[-1])
        self._stack[-1].nodes.append(node)
        if tag not in VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag, {k.lower(): (v if v is not None else "") for k, v in attrs}, self._stack[-1])
        self._stack[-1].nodes.append(node)

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                del self._stack[i:]
                return

    def handle_data(self, data: str) -> None:
        if data.strip() and self._stack[-1].tag not in ("script", "style"):
            self._stack[-1].nodes.append(data)


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


class _HtmlExtractor:
    """Pure-Python twin of :data:`EXTRACT_JS` - keep the two in step."""

    _SIMPLE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")

    def __init__(self, html: str, url: str = "") -> None:
        parser = _DomParser()
        parser.feed(html)
        parser.close()
        self.root = parser.root
        self.url = url
        self.all_nodes = list(self.root.descendants())
        self.labels_for: dict[str, _Node] = {}
        self.by_id: dict[str, list[_Node]] = {}
        self._tag_name: dict[tuple[str, str], int] = {}
        self._tag_type: dict[tuple[str, str], int] = {}
        for node in self.all_nodes:
            node_id = node.get("id")
            if node_id:
                self.by_id.setdefault(node_id, []).append(node)
            if node.tag == "label":
                key = node.get("for")
                if key and key not in self.labels_for:
                    self.labels_for[key] = node
            name = node.get("name")
            if name:
                self._tag_name[(node.tag, name)] = self._tag_name.get((node.tag, name), 0) + 1
            type_ = node.get("type")
            if type_:
                self._tag_type[(node.tag, type_)] = self._tag_type.get((node.tag, type_), 0) + 1

    # -- selectors
    def path_selector(self, el: _Node) -> str:
        parts: list[str] = []
        node: _Node | None = el
        while node is not None and node.tag not in ("body", "html", "#document"):
            parent = node.parent
            idx = 1
            if parent is not None:
                sibs = [c for c in parent.children if c.tag == node.tag]
                idx = sibs.index(node) + 1
            parts.insert(0, f"{node.tag}:nth-of-type({idx})")
            node = parent
        return " > ".join(parts)

    def unique_selector(self, el: _Node) -> str:
        el_id = el.get("id")
        if el_id and self._SIMPLE_ID.match(el_id) and len(self.by_id.get(el_id, [])) == 1:
            return f"#{el_id}"
        name = el.get("name")
        if name and self._tag_name.get((el.tag, name), 0) == 1:
            return f'{el.tag}[name="{name}"]'
        type_ = el.get("type")
        if type_ and self._tag_type.get((el.tag, type_), 0) == 1:
            return f'{el.tag}[type="{type_}"]'
        return self.path_selector(el)

    # -- labels
    def _preceding_text(self, el: _Node) -> str | None:
        for sib in el.previous_siblings()[:3]:
            text = sib.text()
            if text:
                return text
        if el.parent is not None and el.parent.own_text():
            return el.parent.own_text()
        return None

    def own_label(self, el: _Node) -> tuple[str | None, str]:
        el_id = el.get("id")
        if el_id and el_id in self.labels_for:
            return self.labels_for[el_id].text(), "label[for]"
        aria = _clean(el.get("aria-label"))
        if aria:
            return aria, "aria-label"
        by = el.get("aria-labelledby")
        if by:
            joined = _clean(" ".join(self.by_id[r][0].text() for r in by.split() if self.by_id.get(r)))
            if joined:
                return joined, "aria-labelledby"
        wrap = el.closest("label")
        if wrap is not None and wrap.text():
            return wrap.text(), "wrapping-label"
        placeholder = _clean(el.get("placeholder"))
        if placeholder:
            return placeholder, "placeholder"
        preceding = self._preceding_text(el)
        if preceding:
            return preceding, "preceding-text"
        name = el.get("name")
        if name:
            return name, "name"
        return None, "none"

    def group_label(self, el: _Node) -> str | None:
        fieldset = el.closest("fieldset")
        if fieldset is not None:
            legend = next((n for n in fieldset.descendants() if n.tag == "legend"), None)
            if legend is not None:
                return legend.text()
        box = next(
            (a for a in el.ancestors() if {"field", "form-field", "form-group"} & set(a.classes()) or a.has("data-field")),
            None,
        )
        if box is not None:
            lab = next(
                (n for n in box.descendants() if (n.tag in ("label", "legend") or "label" in n.classes()) and not n.contains(el)),
                None,
            )
            if lab is not None:
                return lab.text()
        return self._preceding_text(el.parent or el)

    def section_of(self, el: _Node) -> str | None:
        for ancestor in el.ancestors():
            if ancestor.tag in ("body", "html", "#document"):
                break
            if ancestor.tag == "fieldset":
                legend = next((n for n in ancestor.descendants() if n.tag == "legend" and not n.contains(el)), None)
                if legend is not None:
                    return legend.text()
            heading = next((n for n in ancestor.descendants() if n.tag in HEADING_TAGS and not n.contains(el)), None)
            if heading is not None:
                return heading.text()
        return None

    # -- extraction
    def extract(self) -> dict[str, Any]:
        fields: list[dict[str, Any]] = []
        for el in self.all_nodes:
            if el.tag not in ("input", "select", "textarea"):
                continue
            type_ = (el.get("type") or "").lower()
            if el.tag == "input" and type_ in SKIP_INPUT_TYPES:
                continue
            style = re.sub(r"\s+", "", (el.get("style") or "")).lower()
            if el.has("hidden") or "display:none" in style or "visibility:hidden" in style:
                continue
            if any(a.tag in CHROME_TAGS for a in el.ancestors()):
                continue
            label, label_source = self.own_label(el)
            options: list[dict[str, Any]] = []
            if el.tag == "select":
                for opt in (n for n in el.descendants() if n.tag == "option"):
                    value = opt.get("value")
                    options.append({"value": opt.text() if value is None else value, "label": opt.text(), "selector": None})
            fields.append(
                {
                    "tag": el.tag,
                    "type": type_,
                    "name": el.get("name"),
                    "id": el.get("id"),
                    "placeholder": el.get("placeholder"),
                    "autocomplete": el.get("autocomplete"),
                    "required": el.has("required") or (el.get("aria-required") or "").lower() == "true",
                    "disabled": el.has("disabled"),
                    "label": label,
                    "label_source": label_source,
                    "group_label": self.group_label(el) if type_ == "radio" else None,
                    "value": el.get("value"),
                    "options": options,
                    "selector": self.unique_selector(el),
                    "section": self.section_of(el),
                }
            )

        submit = None
        by_type = next(
            (n for n in self.all_nodes if (n.tag == "button" or n.tag == "input") and (n.get("type") or "").lower() == "submit"),
            None,
        )
        if by_type is not None:
            submit = self.unique_selector(by_type)
        else:
            hit = next(
                (
                    n
                    for n in self.all_nodes
                    if n.tag == "button" and re.search(r"submit|apply|send application", f"{n.text()} {n.get('value') or ''}", re.I)
                ),
                None,
            )
            if hit is not None:
                submit = self.unique_selector(hit)

        captcha: list[dict[str, str]] = []

        def _push(selector: str, detail: str) -> None:
            if not any(c["selector"] == selector for c in captcha):
                captcha.append({"selector": selector, "detail": detail})

        for selector, predicate in (
            (".g-recaptcha", lambda n: "g-recaptcha" in n.classes()),
            (".h-captcha", lambda n: "h-captcha" in n.classes()),
            (".cf-turnstile", lambda n: "cf-turnstile" in n.classes()),
            ("[data-sitekey]", lambda n: n.has("data-sitekey")),
            ("#captcha", lambda n: n.get("id") == "captcha"),
            (".captcha", lambda n: "captcha" in n.classes()),
        ):
            if any(predicate(n) for n in self.all_nodes):
                _push(selector, selector)
        for frame in (n for n in self.all_nodes if n.tag == "iframe"):
            src = (frame.get("src") or "").lower()
            for token in CAPTCHA_TOKENS:
                if token in src:
                    _push(f'iframe[src*="{token}"]', src[:200])

        headings = [n.text() for n in self.all_nodes if n.tag in ("h1", "h2", "h3") and n.text()]
        body = next((n for n in self.all_nodes if n.tag == "body"), self.root)
        title_node = next((n for n in self.all_nodes if n.tag == "title"), None)
        return {
            "url": self.url,
            "title": title_node.text() if title_node is not None else "",
            "fields": fields,
            "submit_selector": submit,
            "captcha": captcha,
            "headings": headings,
            "text_sample": body.text()[:6000],
        }


def detect_form_from_html(html: str, url: str = "") -> DetectedForm:
    """Browser-free twin of :func:`detect_form` (same rules, ``html.parser`` only)."""
    return _finalize(_HtmlExtractor(html, url).extract())


# --------------------------------------------------------------------------- shared rules


def _field_type(raw: dict[str, Any]) -> FieldType:
    if raw["tag"] == "select":
        return FieldType.SELECT
    if raw["tag"] == "textarea":
        return FieldType.TEXTAREA
    return _TYPE_MAP.get(raw.get("type") or "", FieldType.TEXT)


def _is_required(raw: dict[str, Any], label: str | None) -> bool:
    if raw.get("required"):
        return True
    return "*" in (label or "")


def _options(raw: dict[str, Any]) -> list[FieldOption]:
    out: list[FieldOption] = []
    for opt in raw.get("options") or []:
        value = (opt.get("value") or "").strip()
        label = _clean(opt.get("label")) or value
        if not value and (not label or re.match(r"^(--|select|choose|please)", label, re.I)):
            continue  # placeholder option
        out.append(FieldOption(value=value or label, label=label, selector=opt.get("selector")))
    return out


def _group_selector(raw: dict[str, Any]) -> str:
    name = raw.get("name")
    return f'input[type="radio"][name="{name}"]' if name else raw["selector"]


def _build_fields(raw_fields: list[dict[str, Any]]) -> list[DetectedField]:
    fields: list[DetectedField] = []
    radio_index: dict[str, int] = {}
    for raw in raw_fields:
        field_type = _field_type(raw)
        label = _clean(raw.get("label")) or None
        if field_type is FieldType.RADIO:
            # one DetectedField per radio *group*, options carry the individual choices
            key = raw.get("name") or raw["selector"]
            option = FieldOption(
                value=raw.get("value") or label or "",
                label=label or raw.get("value") or "",
                selector=raw["selector"],
            )
            if key in radio_index:
                group = fields[radio_index[key]]
                group.options.append(option)
                group.required = group.required or _is_required(raw, raw.get("group_label"))
                continue
            group_label = _clean(raw.get("group_label")) or label
            radio_index[key] = len(fields)
            fields.append(
                DetectedField(
                    selector=_group_selector(raw),
                    label=group_label,
                    name=raw.get("name"),
                    id=raw.get("id"),
                    placeholder=raw.get("placeholder"),
                    field_type=FieldType.RADIO,
                    required=_is_required(raw, group_label),
                    options=[option],
                    autocomplete=raw.get("autocomplete"),
                    section=_clean(raw.get("section")) or None,
                )
            )
            continue
        fields.append(
            DetectedField(
                selector=raw["selector"],
                label=label,
                name=raw.get("name"),
                id=raw.get("id"),
                placeholder=raw.get("placeholder"),
                field_type=field_type,
                required=_is_required(raw, label),
                options=_options(raw),
                autocomplete=raw.get("autocomplete"),
                section=_clean(raw.get("section")) or None,
            )
        )
    return fields


def _detect_blockers(raw: dict[str, Any], fields: list[DetectedField]) -> list[Blocker]:
    """Classify everything that forces a human back into the loop. Never bypassed."""
    blockers: list[Blocker] = []
    text = raw.get("text_sample") or ""
    headings = " ".join(raw.get("headings") or [])

    widgets = raw.get("captcha") or []
    if widgets:
        # one pause per page, however many selectors matched the same widget
        blockers.append(
            Blocker(
                kind=PauseReason.CAPTCHA,
                selector=widgets[0].get("selector"),
                message=(
                    "CAPTCHA challenge detected ("
                    + ", ".join(sorted({w.get("selector") or "?" for w in widgets}))
                    + ") - JobPilot never solves CAPTCHAs; please complete it yourself."
                ),
            )
        )
    if not blockers and re.search(r"\bcaptcha\b", text, re.I):
        blockers.append(
            Blocker(
                kind=PauseReason.CAPTCHA,
                selector=None,
                message="The page mentions a CAPTCHA challenge - human verification required.",
            )
        )

    for field in fields:
        blob = " ".join(p for p in (field.label, field.name, field.placeholder, field.id) if p)
        if (field.autocomplete or "").lower() == "one-time-code" or OTP_RE.search(blob):
            blockers.append(
                Blocker(
                    kind=PauseReason.OTP,
                    selector=field.selector,
                    message="A one-time code / 2FA step is required - please provide it yourself.",
                )
            )
            break

    passwords = [f for f in raw.get("fields") or [] if (f.get("type") or "") == "password"]
    confirm = [p for p in passwords if CONFIRM_PASSWORD_RE.search(f"{p.get('label') or ''} {p.get('name') or ''}")]
    application_fields = [
        f
        for f in fields
        if f.field_type in (FieldType.FILE, FieldType.TEXTAREA) or APPLICATION_FIELD_RE.search(f.text_blob())
    ]
    if passwords and REGISTER_TEXT_RE.search(headings or text) and confirm:
        blockers.append(
            Blocker(
                kind=PauseReason.ACCOUNT_REGISTRATION_REQUIRED,
                selector=passwords[0].get("selector"),
                message="This site requires creating an account before applying - please register yourself.",
            )
        )
    elif passwords and LOGIN_TEXT_RE.search(text) and not application_fields:
        blockers.append(
            Blocker(
                kind=PauseReason.LOGIN_REQUIRED,
                selector=passwords[0].get("selector"),
                message="A sign-in wall was detected - please log in with your own credentials.",
            )
        )
    return blockers


def _finalize(raw: dict[str, Any]) -> DetectedForm:
    """Turn the raw structural payload (JS or HTML side) into a DetectedForm."""
    raw_fields = [f for f in (raw.get("fields") or []) if not f.get("disabled")]
    fields = _build_fields(raw_fields)
    raw_with_all = dict(raw)
    raw_with_all["fields"] = raw.get("fields") or []
    return DetectedForm(
        url=raw.get("url") or "",
        fields=fields,
        submit_selector=raw.get("submit_selector"),
        blockers=_detect_blockers(raw_with_all, fields),
    )
