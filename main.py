"""Windows GUI entry point; --cli provides a console interface for automation."""
import argparse
import json
import sys
from dataclasses import asdict
from xsf_converter.core import convert, diagnostic

def main():
    if len(sys.argv) == 1:
        from xsf_converter.gui import main as gui
        gui();return
    parser=argparse.ArgumentParser(description="XSF/XSTM v1 → SF2 streaming converter")
    parser.add_argument("--cli", action="store_true", help="Use the command line")
    parser.add_argument("source")
    parser.add_argument("destination")
    parser.add_argument("--force", action="store_true", help="Replace an existing output")
    parser.add_argument("--diagnostic", action="store_true")
    args=parser.parse_args()
    try:
        if args.diagnostic:
            diagnostic(args.source,args.destination)
        else:
            result=convert(args.source,args.destination,overwrite=args.force)
            print(json.dumps(dict(path=str(result.path),sha256=result.sha256,**asdict(result.info)),ensure_ascii=False))
    except Exception as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)

if __name__=="__main__":
    main()
