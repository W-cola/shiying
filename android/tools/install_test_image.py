"""Download the official test image with resumable HTTPS and verify its manifest checksum."""
import hashlib
import json
import os
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
import requests

root=Path(__file__).resolve().parents[2]
base='https://dl.google.com/android/repository/sys-img/google_apis/'
response=requests.get(base+'sys-img2-3.xml',timeout=40); response.raise_for_status()
repository=ET.fromstring(response.content)
local=lambda tag: tag.rsplit('}',1)[-1]
package=next(node for node in repository.iter() if local(node.tag)=='remotePackage' and node.get('path')=='system-images;android-35;google_apis;x86_64')
archive=next(node for node in package.iter() if local(node.tag)=='complete')
values={local(node.tag):node.text for node in archive}
uri=base+values['url']; expected_size=int(values['size']); expected_hash=values['checksum']
dest=root/'.android-build/downloads'/values['url']; dest.parent.mkdir(parents=True,exist_ok=True)
print('Official image:',values['url'],'bytes:',expected_size,flush=True)
for attempt in range(5):
    offset=dest.stat().st_size if dest.exists() else 0
    if offset==expected_size: break
    headers={'Range':f'bytes={offset}-'} if offset else {}
    try:
        with requests.get(uri,headers=headers,stream=True,timeout=(15,60)) as download:
            download.raise_for_status()
            append=offset>0 and download.status_code==206
            if not append: offset=0
            with dest.open('ab' if append else 'wb') as output:
                last=time.monotonic()
                for chunk in download.iter_content(1024*1024):
                    output.write(chunk); offset+=len(chunk)
                    if time.monotonic()-last>15:
                        print(f'Image download: {offset/expected_size:.0%} ({offset//1048576} MB)',flush=True); last=time.monotonic()
    except requests.RequestException as error:
        print('Retrying image transfer:',type(error).__name__,flush=True)
assert dest.stat().st_size==expected_size,'Incomplete system image'
h=hashlib.sha1()
with dest.open('rb') as stream:
    for block in iter(lambda:stream.read(1024*1024),b''): h.update(block)
assert h.hexdigest()==expected_hash,'Official image checksum mismatch'
image=root/'.android-build/sdk/system-images/android-35/google_apis/x86_64'
image.mkdir(parents=True,exist_ok=True)
print('Extracting verified image...',flush=True)
with zipfile.ZipFile(dest) as bundle:
    for item in bundle.infolist():
        parts=Path(item.filename).parts
        if parts[0]!='x86_64': continue
        target=image.joinpath(*parts[1:])
        assert target.resolve().is_relative_to(image.resolve())
        if item.is_dir(): target.mkdir(parents=True,exist_ok=True)
        else:
            target.parent.mkdir(parents=True,exist_ok=True)
            with bundle.open(item) as source,target.open('wb') as output:
                import shutil
                shutil.copyfileobj(source,output,1024*1024)
print('System image ready:',image,flush=True)
