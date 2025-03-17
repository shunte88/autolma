import sys
import os
import re
import logging
from datetime import datetime
from src.utils import LMADownloader
from pathlib import Path
from argparse import ArgumentParser

sys.path.append(str(Path(__file__).resolve().parent / 'src'))

parser = ArgumentParser()
parser.add_argument('--source', '-s',
                    help='source url',
                    type=str,
                    default=None)
parser.add_argument('--norule','-n',
                    help='Ignore standard Hi-Res rules',
                    type=int,
                    default=0,
                    const=0,
                    nargs='?',
                    choices=[0, 1])
parser.add_argument('--filter', '-f',
                    help='filter',
                    type=str,
                    default=None)
args = parser.parse_args()
print(args)
upo = os.getenv('NTFLR_USERNAME')
if not upo:
    print('NTFLR_USERNAME not set')
    sys.exit(1)

sdx = LMADownloader(
    download_dir=os.getenv(
        'MUSIC_DOWNLOAD_DIR', 
        '/media/stuart/one/pre/'
    ),
    uxs=upo,
    pxs=os.getenv('NTFLR_PREMIUM'),
    source=args.source,
    filter=args.filter,
    apply_rule=(0==args.norule),
    logging_verbose=True)


follow = []
links = sdx.get_download_links()
logging.info(f'Found {len(links)} links')
for link in links:
    follow.append(sdx.load_page(link))

# Close the browser and cleanup
sdx.close()
# Download and rebuild seen files
sdx.download_files(follow)
sdx.rebuild_seen_files()
