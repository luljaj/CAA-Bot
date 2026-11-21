BEGIN;

ALTER TABLE public.stats
    ADD COLUMN steam_id bigint
    CONSTRAINT stats_steam_id_valid
    CHECK (steam_id BETWEEN 76561197960265729 AND 76561202255233023);

CREATE UNIQUE INDEX stats_steam_id_unique
    ON public.stats (steam_id)
    WHERE steam_id IS NOT NULL;

COMMENT ON COLUMN public.stats.steam_id IS
    'Self-reported SteamID64 used to look up Deadlock stats.';

CREATE FUNCTION public.protect_stats_steam_link()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    IF current_user NOT IN ('anon', 'authenticated') THEN
        RETURN NEW;
    END IF;

    IF TG_OP = 'INSERT' THEN
        IF NEW.steam_id IS NULL THEN
            RETURN NEW;
        END IF;
    ELSIF NEW.steam_id IS NOT DISTINCT FROM OLD.steam_id
        AND (NEW.steam_id IS NULL OR NEW.discordid IS NOT DISTINCT FROM OLD.discordid) THEN
        RETURN NEW;
    END IF;

    RAISE EXCEPTION 'Steam links require a server-side database role' USING ERRCODE = '42501';
END;
$$;

CREATE TRIGGER protect_stats_steam_link
    BEFORE INSERT OR UPDATE OF steam_id, discordid ON public.stats
    FOR EACH ROW EXECUTE FUNCTION public.protect_stats_steam_link();

REVOKE EXECUTE ON FUNCTION public.protect_stats_steam_link() FROM PUBLIC, anon, authenticated;

COMMIT;
