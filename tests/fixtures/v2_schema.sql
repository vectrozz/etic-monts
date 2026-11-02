-- Schema of the v2 production database (emb.boblabs.eu) — structure only, no data.
-- Condensed from `pg_dump --schema-only --no-owner --no-privileges` taken on 2026-11-02
-- (serial = integer + owned sequence + nextval default, exactly as in prod).
-- Notable v2 quirks the migrations must handle: fermes.name is VARCHAR(20) with
-- NO unique constraint, and there is no role / is_active column.

CREATE TABLE public.fermes (
    id serial PRIMARY KEY,
    name character varying(20),
    userpass character varying(100),
    farmname character varying(100),
    adress character varying(100),
    integration_year character varying(100),
    created_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    last_login_date timestamp without time zone
);

CREATE TABLE public.surface (
    id serial PRIMARY KEY,
    linked_id integer REFERENCES public.fermes(id) ON DELETE CASCADE,
    year integer,
    surftot numeric(10,4),
    surffr numeric(10,4),
    surfgf numeric(10,4),
    surfleg numeric(10,4),
    prairie numeric(10,4),
    culture numeric(10,4),
    surfautre numeric(10,4),
    CONSTRAINT surface_year_check CHECK (((year >= 2010) AND (year <= 2100)))
);

CREATE TABLE public.biodiv (
    id serial PRIMARY KEY,
    linked_id integer REFERENCES public.fermes(id) ON DELETE CASCADE,
    year integer,
    haie numeric(10,4),
    arbrealign numeric(10,4),
    arbreseul numeric(10,4),
    bosquet numeric(10,4),
    mare numeric(10,4),
    fosse numeric(10,4),
    bordure numeric(10,4),
    jachere numeric(10,4),
    jacheremel numeric(10,4),
    muret numeric(10,4),
    description text,
    biodivscore numeric(10,4),
    CONSTRAINT biodiv_year_check CHECK (((year >= 2010) AND (year <= 2100)))
);

CREATE TABLE public.coefbiodiv (
    id serial PRIMARY KEY,
    year integer UNIQUE,
    coefhaie numeric(10,4),
    coefarbrealign numeric(10,4),
    coefarbreseul numeric(10,4),
    coefbosquet numeric(10,4),
    coefmare numeric(10,4),
    coeffosse numeric(10,4),
    coefbordure numeric(10,4),
    coefjachere numeric(10,4),
    coefjacheremel numeric(10,4),
    coefmuret numeric(10,4),
    coefprairie numeric(10,4),
    description text,
    CONSTRAINT coefbiodiv_year_check CHECK (((year >= 2010) AND (year <= 2100)))
);

CREATE TABLE public.plastique (
    id serial PRIMARY KEY,
    linked_id integer REFERENCES public.fermes(id) ON DELETE CASCADE,
    year integer,
    surftotplast numeric(10,2),
    surftottoile numeric(10,2),
    paillagefr jsonb,
    paillagegf jsonb,
    paillageleg jsonb,
    limitation jsonb,
    embplast jsonb,
    embplastpourcent numeric(5,2),
    embfr jsonb,
    embgf jsonb,
    embleg jsonb,
    CONSTRAINT plastique_embplastpourcent_check CHECK (((embplastpourcent >= (0)::numeric) AND (embplastpourcent <= (100)::numeric))),
    CONSTRAINT plastique_year_check CHECK (((year >= 2010) AND (year <= 2100)))
);

CREATE TABLE public.soil (
    id serial PRIMARY KEY,
    linked_id integer REFERENCES public.fermes(id) ON DELETE CASCADE,
    year integer,
    soilanalyse jsonb,
    connaissance integer,
    formation jsonb,
    pratique jsonb,
    CONSTRAINT soil_connaissance_check CHECK (((connaissance >= 0) AND (connaissance <= 10))),
    CONSTRAINT soil_year_check CHECK (((year >= 2010) AND (year <= 2100)))
);

CREATE TABLE public.water (
    id serial PRIMARY KEY,
    linked_id integer REFERENCES public.fermes(id) ON DELETE CASCADE,
    year integer,
    matosirrigfr jsonb,
    matosirriggf jsonb,
    matosirrigleg jsonb,
    consoeau numeric(10,4),
    actions jsonb,
    CONSTRAINT water_year_check CHECK (((year >= 2010) AND (year <= 2100)))
);

CREATE TABLE public.lutte (
    id serial PRIMARY KEY,
    linked_id integer REFERENCES public.fermes(id) ON DELETE CASCADE,
    year integer,
    achat jsonb,
    favorisation jsonb,
    formation jsonb,
    CONSTRAINT lutte_year_check CHECK (((year >= 2010) AND (year <= 2100)))
);
