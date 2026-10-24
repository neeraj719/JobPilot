import {
  AlignLeft,
  Award,
  BadgeCheck,
  Briefcase,
  FolderGit2,
  GraduationCap,
  Languages,
  type LucideIcon,
  UserRound,
  Wrench,
} from 'lucide-react'

import type { SectionKey } from '../../types'

/** One icon per resume section (editor rail chips and section headers). */
export const SECTION_ICONS: Record<SectionKey | 'header', LucideIcon> = {
  header: UserRound,
  summary: AlignLeft,
  skills: Wrench,
  experience: Briefcase,
  projects: FolderGit2,
  education: GraduationCap,
  certifications: BadgeCheck,
  achievements: Award,
  languages: Languages,
}
