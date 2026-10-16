"""Run local TenderLens browser demo: no LAN binding or debug console."""
import argparse
import socket
from pathlib import Path
from .app import create_app

def main():
    parser=argparse.ArgumentParser(description='TenderLens M07 loopback-only browser app')
    parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    if not (1024<=args.port<=65535):parser.error('port 1024..65535 required')
    app=create_app(args.data_root)
    print(f'TENDERLENS_LOCAL_URL=http://127.0.0.1:{args.port}/',flush=True)
    print('LOOPBACK_ONLY=TRUE. No external APIs. Press Ctrl+C to stop.',flush=True)
    app.run(host='127.0.0.1',port=args.port,debug=False,use_reloader=False,threaded=False)

if __name__=='__main__':main()
