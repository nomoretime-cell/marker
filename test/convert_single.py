import argparse
import time

from marker.convert import convert_single_pdf
from marker.logger import configure_logging
from marker.models import load_all_models
from marker.settings import settings
import json
import signal

configure_logging()

def handler(signum, frame):
    pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("filename", help="PDF file to parse")
    parser.add_argument("output", help="Output file name")
    parser.add_argument("--max_pages", type=int, default=None, help="Maximum number of pages to parse")
    parser.add_argument("--parallel_factor", type=int, default=1, help="How much to multiply default parallel OCR workers and model batch sizes by.")
    args = parser.parse_args()

    fname = args.filename
    start_time = time.time()
    model_lst = load_all_models()
    end_time = time.time()
    execution_time = end_time - start_time
    print(f"Function '{load_all_models.__name__}' took {execution_time} seconds to execute.")
    
    start_time = time.time()
    full_text, out_meta = convert_single_pdf(fname, model_lst, max_pages=args.max_pages, parallel_factor=args.parallel_factor)
    end_time = time.time()
    execution_time = end_time - start_time
    print(f"Function '{convert_single_pdf.__name__}' took {execution_time} seconds to execute.")

    with open(args.output, "w+", encoding='utf-8') as f:
        f.write(full_text)

    out_meta_filename = args.output.rsplit(".", 1)[0] + "_meta.json"
    with open(out_meta_filename, "w+") as f:
        f.write(json.dumps(out_meta, indent=4))
    
    # Wait for Stop
    signal.signal(signal.SIGINT, handler)
    signal.pause()