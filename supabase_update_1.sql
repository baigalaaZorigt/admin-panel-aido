-- =========================================================
-- Өөрчлөлт 1: content_drafts-д «rejected» (Татгалзсан) төлөв нэмэх
-- Supabase SQL Editor дээр нэг удаа ажиллуулна.
-- =========================================================

alter table public.content_drafts drop constraint if exists content_drafts_status_check;

alter table public.content_drafts add constraint content_drafts_status_check
  check (status in ('draft', 'review', 'published', 'rejected'));
