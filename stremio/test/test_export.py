"""Check that the D1 exporter produces valid and atomically activated SQL."""
import importlib.util
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('export_catalogue',ROOT/'scripts/export_catalogue.py')
exporter=importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)

class ExportTests(unittest.TestCase):
 def test_export_stages_then_activates_and_preserves_special_characters(self):
  with tempfile.TemporaryDirectory() as folder:
   src=Path(folder)/'source.sqlite'
   conn=sqlite3.connect(src)
   try:
    conn.executescript("""
CREATE TABLE pelis(tmdb INTEGER,titulo TEXT,plot TEXT,poster TEXT,fondo TEXT,genero TEXT,fecha TEXT,rating TEXT,categoria TEXT,updated TEXT);
CREATE TABLE series(tmdb INTEGER,titulo TEXT,plot TEXT,poster TEXT,fondo TEXT,genero TEXT,fecha TEXT,rating TEXT,categoria TEXT,updated TEXT);
CREATE TABLE enlaces_pelis(tmdb INTEGER,link TEXT,calidad TEXT,audio TEXT,info TEXT);
CREATE TABLE enlaces_series(tmdb INTEGER,temporada INTEGER,episodio INTEGER,link TEXT,calidad TEXT,audio TEXT,info TEXT);
INSERT INTO pelis VALUES(123,'An ''example'' movie','A plot?','/poster.jpg',NULL,'Action#Drama','2026-01-01','7.2','Película','2026-11-05');
INSERT INTO series VALUES(456,'A series','Series plot','/series.jpg',NULL,'Comedy','2025-01-01','8.0','General','2026-11-05');
INSERT INTO enlaces_pelis VALUES(123,'https://example.com/movie','1080p','EN',NULL);
INSERT INTO enlaces_series VALUES(456,1,2,'https://example.com/episode','720p','ES',NULL);
""")
   finally:conn.close()
   out=Path(folder)/'out'
   result=exporter.export_database(src,out,'a'*24,{'repo':'fixture/catalogue','sha':'hash'})
   self.assertEqual(result['counts']['catalogue_items'],2)
   self.assertEqual(result['counts']['catalogue_episodes'],1)
   self.assertEqual(result['counts']['catalogue_links'],2)
   files=sorted(out.glob('*.sql'))
   self.assertEqual(files[0].name,'0000-reset.sql')
   self.assertEqual(files[-1].name,'9999-activate.sql')
   target=sqlite3.connect(':memory:')
   try:
    target.executescript((ROOT/'migrations/0001_catalogue.sql').read_text())
    for file in files:target.executescript(file.read_text())
    self.assertEqual(target.execute(
     "SELECT value FROM catalogue_state WHERE key='active_generation'").fetchone()[0],'a'*24)
    self.assertEqual(target.execute('SELECT count(*) FROM catalogue_items').fetchone()[0],2)
    self.assertEqual(target.execute('SELECT count(*) FROM catalogue_links').fetchone()[0],2)
    self.assertEqual(target.execute('SELECT title FROM catalogue_items WHERE tmdb=123').fetchone()[0],
     "An 'example' movie")
   finally:target.close()
   self.assertEqual(json.loads((out/'manifest.json').read_text())['generation'],'a'*24)
if __name__=='__main__':unittest.main()
