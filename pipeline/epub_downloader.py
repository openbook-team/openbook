import io
import sys
import os
import os.path
import csv
import argparse
import requests
import random
import boto3

default_epubs_directory = './epubs/'
default_cache_directory = './cache/'
default_csv_path = './cache/pg_catalog.csv'

GUTENBERG_MIRROR = "https://gutenberg.readingroo.ms/cache/epub"
ebook_link_unformatted = GUTENBERG_MIRROR + "/{}/pg{}-images.epub"

BUCKET_NAME = "gutenberg-vivlia"


def prepare_args():
    def unsigned_int(value):
        i = int(value)
        if(i < 0):
            raise argparse.ArgumentTypeError(
                f"{value} not a valid unsigned integer")
        return i

    parser = argparse.ArgumentParser(
        description='Download ebooks from gutenberg')

    parser.add_argument('--output', default=default_epubs_directory,
                        help="Folder where the epubs files go")
    parser.add_argument(
        '--id', help="Download book associated with specified ID")
    parser.add_argument('--random', '-r', action='store_true',
                        help="Download Random Books")
    parser.add_argument('--upload_s3', '-s3',
                        action='store_true', help="Upload Book(s) to AWS S3")
    parser.add_argument('--all', '-a', action='store_true',
                        help="Download All books from gutenberg")
    parser.add_argument('--max', type=unsigned_int, default=5,
                        help="Maximum books to download, applies to --all/--random [default: 5, unlimited: 0]")

    parser.add_argument('--clear-cache', action='store_true',
                        help="Cache is used to store csv to speed subsequent reads, clear cache if you expect the csv to be out of date")

    args = parser.parse_args()

    if(not (args.id or args.all or args.random)):
        parser.error(
            "you must specify one of the following arguments --all --random or --id")

    if(args.random and args.all):
        parser.error("you can't specify both --random & --all")

    if(args.random and args.max == 0):
        parser.error(
            "--random does not accept --max 0, use --all --max 0 instead")

    return args


def get_epub_link(id):
    return ebook_link_unformatted.format(id, id)


def download_file(link, f):
    """Streams a file from an HTTP(S) URL to a file-like object.

    Arguments:
        link {str} -- The URL to download
        f {file} -- The file-like object to write to

    Returns:
        None
    """
    filename = link.split('/')[-1]
    r = requests.get(link, stream=True)
    if(r.status_code != 200):
        raise FileNotFoundError(f"404: {link}")
    total_length = r.headers.get('content-length')

    # https://stackoverflow.com/a/15645088
    if total_length is None:  # no content length header
        f.write(r.content)
    else:
        processed = 0
        total_length = int(total_length)
        for data in r.iter_content(chunk_size=4096):
            processed += len(data)
            f.write(data)
            done = int(50 * processed / total_length)
            sys.stdout.write(
                "\rDownloading: {} - [{}{}] {}%".format(filename, '=' * done, ' ' * (50-done), done * 2))
            sys.stdout.flush()
        print("")


def get_csv_reader(save_to_file=True, clear_cache=False):
    """Downloads the csv file from gutenberg.org and returns a csv.reader object

    Keyword Arguments:
        save_to_file {bool} -- If true, saves the csv file to the cache directory [default: {True}]
        clear_cache {bool} -- If true, clears the cache directory [default: {False}]

    Returns:
        csv.reader -- A csv.reader object"""
    if(save_to_file):
        if(clear_cache or not os.path.isfile(default_csv_path)):
            os.makedirs(os.path.dirname(default_csv_path), exist_ok=True)
            with open(default_csv_path, "wb") as f:
                download_file(f'{GUTENBERG_MIRROR}/feeds/pg_catalog.csv', f)

        with open(default_csv_path, "r", encoding='utf-8') as f:
            return csv.DictReader(f.read().splitlines(), delimiter=',', quotechar='"')
    else:
        f = io.BytesIO()
        download_file(f'{GUTENBERG_MIRROR}/feeds/pg_catalog.csv', f)
        f.seek(0)
        strbuf = io.TextIOWrapper(f, 'utf-8', newline='')
        return csv.DictReader(strbuf.read().splitlines(), delimiter=',', quotechar='"')


def upload_ebook_s3(id):
    """Uploads an ebook to the AWS S3 bucket

    Arguments:
        id {int} -- The id of the ebook to upload

    Returns:
        str -- The path of the ebook on the AWS S3 bucket"""
    ebook_link = get_epub_link(id)
    filename = ebook_link.split('/')[-1]
    path = os.path.join(default_epubs_directory, filename)

    f = io.BytesIO()
    download_file(ebook_link, f)
    f.seek(0)
    s3_client = boto3.resource('s3')
    response = s3_client.meta.client.upload_fileobj(f, BUCKET_NAME, filename)

    return f"s3://{BUCKET_NAME}/{filename}"


def download_ebook(id):
    """Downloads an ebook from gutenberg.org

    Arguments:
        id {int} -- The id of the ebook to download

    Returns:
        str -- The path of the ebook on the local filesystem"""
    ebook_link = get_epub_link(id)
    filename = ebook_link.split('/')[-1]
    path = os.path.join(default_epubs_directory, filename)
    with open(path, "wb") as f:
        download_file(ebook_link, f)
        return path


def download_ebook_to_temp(id):
    """Downloads an ebook from gutenberg.org to a temporary file

    Arguments:
        id {int} -- The id of the ebook to download

    Returns:
        list -- A list containing the file and the file path"""
    ebook_link = get_epub_link(id)
    filename = ebook_link.split('/')[-1]
    f = open(f'/tmp/{filename}', 'w+b')
    download_file(ebook_link, f)
    f.seek(0)
    return [f, filename]


if __name__ == '__main__':
    args = prepare_args()
    if(args.clear_cache and os.path.isfile(default_csv_path)):
        os.remove(default_csv_path)

    if(args.all):
        books = get_csv_reader(clear_cache=args.clear_cache)

    if(args.random):
        books = random.choices(
            list(get_csv_reader(clear_cache=args.clear_cache)), k=args.max)

    if(args.all or args.random):
        for book in books:
            book_id = book['Text#']
            title = book['Title']
            if(book['Type'] != 'Text'):
                print(f"Not a book, skipping: {book_id}. {title}.")
                continue
            if(args.upload_s3):
                print(f"Uploading S3 {book_id}. {title}.")
                upload_ebook_s3(book_id)
            else:
                print(f"Downloading {book_id}. {title}.")
                download_ebook(book_id)
            args.max -= 1
            if(args.max == 0):
                break

    if(args.id):
        if(args.upload_s3):
            print(f"Uploading S3 {args.id}.")
            upload_ebook_s3(args.id)
        else:
            print(f"Downloading {args.id}.")
            download_ebook(args.id)
