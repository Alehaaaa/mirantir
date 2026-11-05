CREATE TABLE IF NOT EXISTS catalogue_state (key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS catalogue_items (
 generation TEXT NOT NULL, kind TEXT NOT NULL, tmdb INTEGER NOT NULL,
 title TEXT NOT NULL,plot TEXT,poster TEXT,background TEXT,genres TEXT,
 release_date TEXT,rating TEXT,category TEXT,updated TEXT,
 PRIMARY KEY(generation,kind,tmdb));
CREATE INDEX IF NOT EXISTS idx_catalogue_recent ON catalogue_items(generation,kind,updated DESC,tmdb DESC);
CREATE INDEX IF NOT EXISTS idx_catalogue_category ON catalogue_items(generation,kind,category,updated DESC);
CREATE TABLE IF NOT EXISTS catalogue_episodes (
 generation TEXT NOT NULL,tmdb INTEGER NOT NULL,season INTEGER NOT NULL,episode INTEGER NOT NULL,
 PRIMARY KEY(generation,tmdb,season,episode));
CREATE TABLE IF NOT EXISTS catalogue_links (
 generation TEXT NOT NULL,kind TEXT NOT NULL,tmdb INTEGER NOT NULL,
 season INTEGER NOT NULL,episode INTEGER NOT NULL,position INTEGER NOT NULL,
 quality TEXT,audio TEXT,info TEXT,hoster_url TEXT NOT NULL,
 PRIMARY KEY(generation,kind,tmdb,season,episode,position));
CREATE INDEX IF NOT EXISTS idx_catalogue_streams
 ON catalogue_links(generation,kind,tmdb,season,episode,position);
