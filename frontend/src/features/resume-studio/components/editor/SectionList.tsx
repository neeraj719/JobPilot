import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { EyeOff, GripVertical, Plus, UserRound } from 'lucide-react'
import { type LucideIcon } from 'lucide-react'
import * as React from 'react'

import { SECTION_ICONS } from './sectionIcons'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { SimpleTooltip } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

import { SECTION_KEYS, SECTION_LABELS, type SectionKey } from '../../types'

export type EditorPanel = 'header' | SectionKey

export interface SectionListProps {
  order: SectionKey[]
  counts: Partial<Record<SectionKey, number>>
  active: EditorPanel
  onSelect: (panel: EditorPanel) => void
  onReorder: (order: SectionKey[]) => void
  onRemove: (key: SectionKey) => void
  onAdd: (key: SectionKey) => void
}

/**
 * The resume's sections in display order. Drag with the handle, or focus the handle and use
 * Space + arrow keys (dnd-kit keyboard sensor). Removing hides a section from the resume;
 * its content is kept and comes back when the section is added again.
 */
/** Memoised: the editor re-renders on every keystroke; the list only when its props change. */
export const SectionList = React.memo(function SectionList({ order, counts, active, onSelect, onReorder, onRemove, onAdd }: SectionListProps) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )
  const hidden = SECTION_KEYS.filter((key) => !order.includes(key))

  const onDragEnd = (event: DragEndEvent) => {
    const { active: dragged, over } = event
    if (!over || dragged.id === over.id) return
    const from = order.indexOf(dragged.id as SectionKey)
    const to = order.indexOf(over.id as SectionKey)
    if (from < 0 || to < 0) return
    onReorder(arrayMove(order, from, to))
  }

  return (
    <nav aria-label="Resume sections" className="space-y-2">
      <p className="px-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">Sections</p>
      <button
        type="button"
        onClick={() => onSelect('header')}
        aria-current={active === 'header' ? 'true' : undefined}
        className={cn(
          'flex w-full items-center gap-2.5 rounded-xl px-2 py-1.5 text-left text-sm transition-[background-color,box-shadow] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          active === 'header' ? 'border-gradient font-medium shadow-sm' : 'border border-border bg-card hover:bg-accent',
        )}
      >
        <SectionChip icon={UserRound} active={active === 'header'} />
        Name &amp; contact
      </button>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={order} strategy={verticalListSortingStrategy}>
          <ul className="space-y-1.5">
            {order.map((key) => (
              <SortableRow
                key={key}
                id={key}
                count={counts[key] ?? 0}
                active={active === key}
                onSelect={() => onSelect(key)}
                onRemove={() => onRemove(key)}
              />
            ))}
          </ul>
        </SortableContext>
      </DndContext>
      {hidden.length ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="outline" size="sm" className="w-full">
              <Plus aria-hidden /> Add section
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-56">
            <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">Hidden sections keep their content</DropdownMenuLabel>
            {hidden.map((key) => (
              <DropdownMenuItem key={key} onSelect={() => onAdd(key)}>
                {SECTION_LABELS[key]}
                {counts[key] ? <span className="ml-auto text-xs text-muted-foreground">{counts[key]}</span> : null}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </nav>
  )
})

function SortableRow({
  id,
  count,
  active,
  onSelect,
  onRemove,
}: {
  id: SectionKey
  count: number
  active: boolean
  onSelect: () => void
  onRemove: () => void
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({ id })
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        'flex items-center gap-0.5 rounded-xl pr-1 text-sm transition-shadow',
        active ? 'border-gradient shadow-sm' : 'border border-border bg-card',
        isDragging && 'z-10 shadow-lg',
      )}
    >
      <button
        type="button"
        ref={setActivatorNodeRef}
        {...attributes}
        {...listeners}
        aria-label={`Reorder ${SECTION_LABELS[id]} (Space, then arrow keys)`}
        className="cursor-grab touch-none rounded-lg p-1.5 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:cursor-grabbing"
      >
        <GripVertical className="size-4" aria-hidden />
      </button>
      <SectionChip icon={SECTION_ICONS[id]} active={active} />
      <button
        type="button"
        onClick={onSelect}
        aria-current={active ? 'true' : undefined}
        className={cn('flex min-w-0 flex-1 items-center gap-2 py-2 pl-1.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', active && 'font-medium')}
      >
        <span className="truncate">{SECTION_LABELS[id]}</span>
        {count ? (
          <Badge variant="muted" className="px-1.5 py-0 text-[10px]">
            {count}
          </Badge>
        ) : (
          <span className="text-[11px] text-muted-foreground">empty</span>
        )}
      </button>
      <SimpleTooltip label="Hide from the resume (content is kept)" side="top">
        <Button type="button" variant="ghost" size="icon-sm" aria-label={`Hide ${SECTION_LABELS[id]}`} onClick={onRemove}>
          <EyeOff aria-hidden />
        </Button>
      </SimpleTooltip>
    </li>
  )
}

/** Small icon chip for a section row: soft brand tint, solid gradient when active. */
function SectionChip({ icon: Icon, active }: { icon: LucideIcon; active: boolean }) {
  return (
    <span
      className={cn(
        'flex size-7 shrink-0 items-center justify-center rounded-lg',
        active ? 'bg-gradient-brand text-gradient-foreground' : 'bg-gradient-brand-soft text-primary',
      )}
      aria-hidden
    >
      <Icon className="size-3.5" />
    </span>
  )
}
