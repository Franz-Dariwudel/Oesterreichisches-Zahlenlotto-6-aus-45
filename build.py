"""Saubere Quellcode- und Python-3.12-Bytecode-Auslieferung, GPL-3.0-only."""
from pathlib import Path
import py_compile,shutil,tarfile,tempfile
from lotto45 import VERSION

root=Path(__file__).resolve().parent
out=root/'dist';out.mkdir(exist_ok=True)
for compiled in (False,True):
 name=f'6aus45-{VERSION}-'+('python312-linux' if compiled else 'source')
 with tempfile.TemporaryDirectory() as tmp:
  stage=Path(tmp)/name;stage.mkdir()
  for folder in ['lotto45','languages','help','resources']:
   shutil.copytree(root/folder,stage/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
  for file in ['README.md','CHANGELOG.md','LICENSE','install.py','build.py','DATABASE.md','DATA_STATUS.md','STATISTICS.md','CONCEPT_IMPLEMENTATION.md','THIRD_PARTY.md','requirements.txt']:
   shutil.copy2(root/file,stage/file)
  if not compiled:shutil.copytree(root/'tests',stage/'tests',ignore=shutil.ignore_patterns('__pycache__'))
  if compiled:
   vendor=root/'.venv/lib/python3.12/site-packages'
   if not (vendor/'matplotlib').is_dir():raise RuntimeError('Matplotlib-Buildumgebung fehlt: requirements.txt in .venv installieren.')
   shutil.copytree(vendor,stage/'vendor',ignore=shutil.ignore_patterns('__pycache__','*.pyc','tests','test','direct_url.json'))
   for path in (stage/'lotto45').glob('*.py'):
    py_compile.compile(str(path),cfile=str(path.with_suffix('.pyc')),dfile='lotto45/'+path.name,doraise=True,optimize=1);path.unlink()
  for folder in ['config','logs','data']:(stage/folder).mkdir()
  with tarfile.open(out/(name+'.tar.gz'),'w:gz') as tar:tar.add(stage,arcname=name)
 print(out/(name+'.tar.gz'))
