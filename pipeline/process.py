import sys
from EpubReader import EpubReader
from sqlite_helper import sqlite_helper
from postgres_helper import postgres_helper
import sqlite3
import os
import shutil
import argparse
from pathlib import Path

default_output_directory = "../interface/service/public/output"
default_database_connection = 'sqlite3'
default_database_directory = '../interface/service/database.sqlite3'

parser = argparse.ArgumentParser(description='Process ebook or ebooks')

parser.add_argument('--output', default=default_output_directory,
                    help="Folder where the resulting files go")
parser.add_argument('--database', default=default_database_directory,
                    help="Location/Connection string to database")
parser.add_argument('--database-connection', default=default_database_connection,
                    choices=['sqlite3', 'postgres'],
                    help="Type of database connection [default: sqlite3]")
parser.add_argument('--keep', action='store_true',
                    help="Do not delete the database and output before starting")
parser.add_argument('--input-dir', default=None,
                    help="Gutenberg archive directory to convert")
parser.add_argument('--input-path', default=None,
                    help="Individual epub to convert")
parser.add_argument('--max', type=int, default=None,
                    help="Maximum books to convert in this run")
parser.add_argument('--dry-run', action='store_true',
                    help="Do not make any changes, simply list stats about what you will change")

args = parser.parse_args()

output_directory = args.output
database_directory = args.database

if(args.database_connection == 'sqlite3'):
    database_helper = sqlite_helper
elif(args.database_connection == 'postgres'):
    database_helper = postgres_helper
else:
    parser.error("invalid or no connection specified")


# TODO: make this script support continuing a previously stopped job
if not args.keep:
    if os.path.exists(output_directory):
        if args.dry_run:
            print(f"Would delete {output_directory}")
        else:
            shutil.rmtree(output_directory)

    if os.path.exists(database_directory):
        if args.dry_run:
            print(f"Would delete {database_directory}")
        else:
            database_helper(database_directory, False).drop_tables()

os.makedirs(output_directory, exist_ok=True)

if args.input_path:
    files = [args.input_path]
elif args.input_dir:
    files = tuple(Path(args.input_dir).rglob("*.epub"))
    if args.max:
        files = files[:args.max]
else:
    parser.error("no input specified, you must specify one of the following arguments --input-dir or --input-path")

print(f"Found {len(files)} files")

if args.dry_run:
    for file in files:
        print(file)

if not args.dry_run:
    con = database_helper(database_directory)
    for file in files:
        epub = EpubReader(file)
        if(not epub.is_valid()):
            print(f"warning: ({file}) not a valid epub")

        processed_epub_output = os.path.join(output_directory, epub.slug)
        for order, chapter_title, chapter_path, chapter_content in epub.get_chapters():
            final_chapter_path = os.path.join(processed_epub_output, chapter_path)
            os.makedirs(os.path.dirname(final_chapter_path), exist_ok=True)
            with open(os.path.join(processed_epub_output, chapter_path), "w", encoding="utf-8") as f:
                f.write(chapter_content)
        book_id = con.add_book(epub.title, epub.author, epub.slug, epub.description)
        con.add_chapters(book_id, epub.get_chapters(), epub.slug)

