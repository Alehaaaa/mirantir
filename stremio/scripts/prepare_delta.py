#!/usr/bin/env python3
"""Export only catalogue changes between two verified upstream SQLite files."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

LIB = Path(__file__).resolve().parents[2] / 'addons/plugin.video.mirantir/resources/lib'
sys.path.insert(0, str(LIB))
import crypto
from export_catalogue import q, number

ITEM_FIELDS = 'tmdb,titulo,plot,poster,fondo,genero,fecha,rating,categoria,updated'

class DeltaWriter:
 def __init__(self, folder, max_writes=20000):
  self.folder=folder;self.max_writes=max_writes;self.index=1
  self.blocks=[];self.writes=0;self.files=[]
 def flush(self):
  if not self.blocks:return
  name=f'{self.index:04d}-data.sql';self.index+=1
  text='BEGIN TRANSACTION;\n'+''.join(self.blocks)+'COMMIT;\n'
  (self.folder/name).write_text(text,encoding='utf8')
  self.files.append({'name':name,'writes':self.writes})
  self.blocks=[];self.writes=0
 def add(self, statements, writes):
  if self.blocks and self.writes+writes>self.max_writes:self.flush()
  self.blocks.extend(statements);self.writes+=writes
 def close(self):self.flush()

def rows(conn, sql):
 return conn.execute(sql).fetchall()

def item_value(generation, kind, fields):
 return (generation,kind,number(fields[0],1))+tuple(fields[1:])

def export_delta(old_db,new_db,out,data_generation,source_generation,source_repo):
 out.mkdir(parents=True,exist_ok=True)
 for file in out.iterdir():
  if file.suffix in ('.sql','.json'):file.unlink()
 writer=DeltaWriter(out);counts={'items_upserted':0,'items_deleted':0,
  'episodes_inserted':0,'episodes_deleted':0,'link_groups_replaced':0}
 conn=sqlite3.connect(str(new_db));conn.execute('ATTACH DATABASE ? AS old',(str(old_db),))
 try:
  for table,kind in [('pelis','movie'),('series','series')]:
   for tmdb, in rows(conn,f'SELECT tmdb FROM old.{table} EXCEPT SELECT tmdb FROM main.{table}'):
    tmdb=number(tmdb,1)
    if tmdb:
     writer.add([f"DELETE FROM catalogue_items WHERE generation={q(data_generation)} AND kind={q(kind)} AND tmdb={tmdb};\n"],4)
     counts['items_deleted']+=1
   for fields in rows(conn,f'SELECT {ITEM_FIELDS} FROM main.{table} EXCEPT SELECT {ITEM_FIELDS} FROM old.{table}'):
    value=item_value(data_generation,kind,fields)
    if value[2] and value[3]:
     columns='generation,kind,tmdb,title,plot,poster,background,genres,release_date,rating,category,updated'
     writer.add([f'INSERT OR REPLACE INTO catalogue_items ({columns}) VALUES ('+
      ','.join(map(q,value))+');\n'],8)
     counts['items_upserted']+=1
  episode_sql='SELECT DISTINCT tmdb,temporada,episodio FROM {db}.enlaces_series'
  for values in rows(conn,episode_sql.format(db='main')+' EXCEPT '+episode_sql.format(db='old')):
   tmdb=number(values[0],1);season=number(values[1],0,10000);episode=number(values[2],0,10000)
   if tmdb and season is not None and episode is not None:
    writer.add([f'INSERT OR IGNORE INTO catalogue_episodes VALUES ({q(data_generation)},{tmdb},{season},{episode});\n'],2)
    counts['episodes_inserted']+=1
  for values in rows(conn,episode_sql.format(db='old')+' EXCEPT '+episode_sql.format(db='main')):
   tmdb=number(values[0],1);season=number(values[1],0,10000);episode=number(values[2],0,10000)
   if tmdb and season is not None and episode is not None:
    writer.add([f'DELETE FROM catalogue_episodes WHERE generation={q(data_generation)} AND tmdb={tmdb} AND season={season} AND episode={episode};\n'],2)
    counts['episodes_deleted']+=1
  specs=[('enlaces_pelis','movie','tmdb,link,calidad,audio,info'),
   ('enlaces_series','series','tmdb,temporada,episodio,link,calidad,audio,info')]
  for table,kind,fields in specs:
   changed=set()
   for db1,db2 in [('main','old'),('old','main')]:
    for row in rows(conn,f'SELECT {fields} FROM {db1}.{table} EXCEPT SELECT {fields} FROM {db2}.{table}'):
     changed.add((number(row[0],1),0,0) if kind=='movie' else
      (number(row[0],1),number(row[1],0,10000),number(row[2],0,10000)))
   for tmdb,season,episode in sorted(x for x in changed if None not in x):
    where=(f'tmdb={tmdb}' if kind=='movie' else
     f'tmdb={tmdb} AND temporada={season} AND episodio={episode}')
    select=('SELECT link,calidad,audio,info FROM main.enlaces_pelis WHERE '+where+' ORDER BY rowid'
     if kind=='movie' else 'SELECT link,calidad,audio,info FROM main.enlaces_series WHERE '+where+' ORDER BY rowid')
    old_count=conn.execute(f'SELECT count(*) FROM old.{table} WHERE '+where).fetchone()[0]
    statements=[f'DELETE FROM catalogue_links WHERE generation={q(data_generation)} AND kind={q(kind)} AND tmdb={tmdb} AND season={season} AND episode={episode};\n']
    inserted=0
    for link,quality,audio,details in rows(conn,select):
     try:hoster=crypto.decrypt_link(link)
     except Exception:continue
     if not hoster or not hoster.startswith(('https://','http://')):continue
     value=(data_generation,kind,tmdb,season,episode,inserted,quality,audio,details,hoster)
     statements.append('INSERT INTO catalogue_links VALUES ('+','.join(map(q,value))+');\n');inserted+=1
    writer.add(statements,(old_count+inserted)*3+1)
    counts['link_groups_replaced']+=1
 finally:
  conn.close();writer.close()
 manifest={'mode':'delta','generation':source_generation,'data_generation':data_generation,
  'source':source_repo,'counts':counts,'files':writer.files,
  'estimated_writes':sum(f['writes'] for f in writer.files)}
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
 return manifest

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--old',type=Path,required=True)
 parser.add_argument('--new',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
 parser.add_argument('--data-generation',required=True);parser.add_argument('--source-generation',required=True)
 parser.add_argument('--source-repo',required=True);args=parser.parse_args()
 print(json.dumps(export_delta(args.old,args.new,args.output,args.data_generation,
  args.source_generation,args.source_repo),indent=2))
if __name__=='__main__':main()
