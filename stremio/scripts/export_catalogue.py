#!/usr/bin/env python3
"""Reuse Mirantir's Palantir sync and export a staged D1 catalogue generation."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import os

LIB = Path(__file__).resolve().parents[2] / 'addons/plugin.video.mirantir/resources/lib'
sys.path.insert(0, str(LIB))
import source
import crypto

COLUMNS = {
 'catalogue_items': ('generation','kind','tmdb','title','plot','poster','background','genres','release_date','rating','category','updated'),
 'catalogue_episodes': ('generation','tmdb','season','episode'),
 'catalogue_links': ('generation','kind','tmdb','season','episode','position','quality','audio','info','hoster_url'),
}
def generation_for(info):
 version=[info['repo'],info['sha'],
  [(p['name'],p['sha']) for p in info.get('patches',[])]]
 return hashlib.sha256(json.dumps(version,sort_keys=True).encode()).hexdigest()[:24]

def q(value):
 if value is None: return 'NULL'
 if isinstance(value,(int,float)): return str(value)
 return "'" + str(value).replace('\x00','').replace("'","''") + "'"

def number(value, minimum=0, maximum=2**53):
 try:
  result=int(value)
  return result if minimum<=result<=maximum else None
 except (ValueError,TypeError): return None

class Writer:
 def __init__(self,folder):
  self.folder=folder;self.index=1;self.file=None;self.size=0
  self.table=None;self.batch=[];self.counts={name:0 for name in COLUMNS}
 def flush(self):
  if not self.batch:return
  if self.file is None or self.size>=3_000_000:
   if self.file:self.file.close()
   self.file=(self.folder / f'{self.index:04d}-data.sql').open('w',encoding='utf8')
   self.index+=1;self.size=0
  sql='INSERT INTO '+self.table+' ('+','.join(COLUMNS[self.table])+') VALUES\n'+',\n'.join(self.batch)+';\n'
  self.file.write(sql);self.size+=len(sql.encode('utf8'));self.batch=[]
 def put(self,table,values):
  if self.table!=table:self.flush();self.table=table
  self.batch.append('('+','.join(map(q,values))+')')
  self.counts[table]+=1
  if len(self.batch)>=75:self.flush()
 def close(self):
  self.flush()
  if self.file:self.file.close()

def export_database(db_path,out,generation,info):
 out.mkdir(parents=True,exist_ok=True)
 for file in out.iterdir():
  if file.suffix in ('.sql','.json'):file.unlink()
 (out/'0000-reset.sql').write_text(''.join(
  'DELETE FROM '+table+' WHERE generation='+q(generation)+';\n'
  for table in ('catalogue_links','catalogue_episodes','catalogue_items')),encoding='utf8')
 writer=Writer(out)
 conn=sqlite3.connect(str(db_path))
 try:
  for table,kind in [('pelis','movie'),('series','series')]:
   for fields in conn.execute(
    'SELECT tmdb,titulo,plot,poster,fondo,genero,fecha,rating,categoria,updated FROM '+table):
    tmdb=number(fields[0],1)
    if tmdb and fields[1]:
     writer.put('catalogue_items',(generation,kind,tmdb)+fields[1:])
  for tmdb,season,episode in conn.execute(
   'SELECT DISTINCT tmdb,temporada,episodio FROM enlaces_series ORDER BY tmdb,temporada,episodio'):
   tmdb=number(tmdb,1);season=number(season,0,10000);episode=number(episode,0,10000)
   if tmdb and season is not None and episode is not None:
    writer.put('catalogue_episodes',(generation,tmdb,season,episode))
  for table,kind in [('enlaces_pelis','movie'),('enlaces_series','series')]:
   query=('SELECT tmdb,0,0,link,calidad,audio,info FROM enlaces_pelis ORDER BY tmdb'
    if kind=='movie' else
    'SELECT tmdb,temporada,episodio,link,calidad,audio,info FROM enlaces_series ORDER BY tmdb,temporada,episodio')
   previous=None;position=0
   for tmdb,season,episode,link,quality,audio,details in conn.execute(query):
    tmdb=number(tmdb,1);season=number(season,0,10000);episode=number(episode,0,10000)
    if not tmdb or season is None or episode is None:continue
    key=(tmdb,season,episode)
    if key!=previous:previous=key;position=0
    try: hoster=crypto.decrypt_link(link)
    except Exception:continue
    if not hoster or not hoster.startswith(('https://','http://')):continue
    writer.put('catalogue_links',(generation,kind,tmdb,season,episode,position,
     quality,audio,details,hoster))
    position+=1
 finally:
  conn.close();writer.close()
 if not writer.counts['catalogue_items']:raise RuntimeError('Empty catalogue; refusing activation')
 (out/'9999-activate.sql').write_text(
  "INSERT OR REPLACE INTO catalogue_state(key,value) VALUES('active_generation',"+q(generation)+");\n"+
  "INSERT OR REPLACE INTO catalogue_state(key,value) VALUES('source_repo',"+q(info['repo'])+");\n",
  encoding='utf8')
 manifest={'generation':generation,'counts':writer.counts,'source':info['repo']}
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
 return manifest

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--output',type=Path,default=Path('.data/import'))
 parser.add_argument('--db',type=Path,help='Existing SQLite file (for local tests)')
 parser.add_argument('--check-only',action='store_true',help='Print upstream generation without downloading the database')
 parser.add_argument('--source-repo',help='Previously verified source repository to check directly')
 args=parser.parse_args()
 if args.source_repo:
  os.environ['PALANTIR_DB_REPO']=args.source_repo
 if args.db:
  info={'repo':'local','sha':hashlib.sha256(args.db.read_bytes()).hexdigest()}
  manifest=export_database(args.db,args.output,info['sha'][:24],info)
 else:
  with tempfile.TemporaryDirectory() as dirname:
   db=Path(dirname)/'moria.cm3';state=Path(dirname)/'state.json'
   info=source.discover(str(state))
   generation=generation_for(info)
   if args.check_only:
    manifest={'generation':generation,'source':info['repo'],'snapshot':info['name'],
     'patches':[p['name'] for p in info.get('patches',[])]}
   else:
    source.sync(str(db),str(state),info=info)
    manifest=export_database(db,args.output,generation,info)
 print(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
