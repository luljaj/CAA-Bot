BEGIN;
DROP FUNCTION public.adddonations(bigint, integer) RESTRICT;
DROP FUNCTION public.fetchdonations(bigint) RESTRICT;
DROP FUNCTION public.top_donations() RESTRICT;
DROP FUNCTION public.addpoints(bigint, integer) RESTRICT;
DROP FUNCTION public.fetchpoints(bigint) RESTRICT;
DROP FUNCTION public.top_points() RESTRICT;
ALTER TABLE public.stats
    DROP COLUMN donations RESTRICT,
    DROP COLUMN points RESTRICT;
COMMIT;
