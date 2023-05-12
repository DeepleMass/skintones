from os import listdir, rename, makedirs
from os.path import join, splitext, exists
from random import shuffle
from hashlib import sha256

inputdir = 'Humans'
outputdir = 'digested'

all_files_names = listdir(inputdir)

all_digests = [ sha256(a_file_name.encode('utf-8')).hexdigest() for a_file_name in all_files_names ]

for aFilename, aDigest in zip(all_files_names,all_digests):
    print ('[', aFilename, end=' ] ')
    targetpath = join(outputdir,aDigest[0])
    makedirs(targetpath, exist_ok=True)
    rename(join(inputdir,aFilename),join(targetpath,aDigest+splitext(aFilename)[-1]))
    
print()