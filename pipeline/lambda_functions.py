from io import BufferedReader
import json
import boto3
from config import config

bucket_name = config["BUCKET_NAME"]
db_connection = config["DB_CONNECTION"]


def UpdateBooks(event, context):
    """Updates books given a list of dictionaries of the book id and the source id. Invokes the update_book function
    for each book.

    Arguments:
        event {dict} -- A dictionary containing the list of dictionaries of the book id and the source id.
        context {object} -- The Lambda context object.

    Returns:
        dict -- A dictionary containing the status of the update.
    """
    # body = {"data": [{"book_id": 1, "ebook_source_id": 1}, ...]}

    data = event['data']
    responses = []
    client = boto3.client('lambda')
    for book in data:
        response = client.invoke(
            FunctionName='updateBook',
            InvocationType='Event',  # 'RequestResponse',
            Payload=json.dumps(book),
        )
        print(response['Payload'].read())
        del response['Payload']
        responses.append(response)

    print(event, context)
    return {
        'statusCode': 202,
        'body': json.dumps(responses),
    }


def UpdateBook(event, context):
    """Updates a book given a dictionary of the book id and the source id.

    Arguments:
        event {dict} -- A dictionary containing the book id and the source id.
        context {object} -- The Lambda context object.

    Returns:
        dict -- A dictionary containing the status of the update."""
    book_id = event['book_id']
    ebook_source_id = event['ebook_source_id']

    from db import db
    with db(db_connection) as con:

        ebook_source = con.get_book_source_by_id(ebook_source_id)
        if(not ebook_source):
            return {
                'statusCode': 200,
                'body': json.dump({'error': "ebook_source not found"})
            }

        import helpers
        url = helpers.parse_s3_url(ebook_source[3])
        epub = helpers.EpubParserFromS3(**url)

        book = con.get_book_by_ebook_source_id(ebook_source_id)
        if(not book):
            return {
                'statusCode': 200,
                'body': json.dump({'error': "book not found"})
            }

        if(ebook_source[0] != ebook_source_id or book[0] != book_id):
            return {
                'statusCode': 200,
                'body': json.dump({'error': "ids mismatch"})
            }

        con.add_chapters(book_id, epub.content.chapters)
        con.add_images(book_id, epub.content.images)

        return {
            'statusCode': 200,
            'body': event
        }


def DownloadBooks(event, context):
    """Downloads books given a list of dictionaries of the gutenberg id and the source id. Invokes the download_book function
    for each book.

    Arguments:
        event {dict} -- A dictionary containing the list of dictionaries of the gutenberg id and the source id.
        context {object} -- The Lambda context object.

    Returns:
        dict -- A dictionary containing the status of the invocation."""
    # body = {"data": [{"gutenberg_id": 1}, ...]}

    data = event['data']
    responses = []
    client = boto3.client('lambda')
    for book in data:
        response = client.invoke(
            FunctionName='downloadBook',
            InvocationType='Event',  # 'RequestResponse',
            Payload=json.dumps(book),
        )
        print(response['Payload'].read())
        del response['Payload']
        responses.append(response)

    print(event, context)
    return {
        'statusCode': 202,
        'body': json.dumps(responses),
    }

# work around to s3 transfer closing buffer
# https://github.com/boto/s3transfer/issues/80#issuecomment-482534256


class NonCloseableBufferedReader(BufferedReader):
    def close(self):
        self.flush()


def DownloadBook(event, context):
    """Downloads a book given a dictionary of the gutenberg id and the source id.

    Arguments:
        event {dict} -- A dictionary containing the gutenberg id and the source id.
        context {object} -- The Lambda context object.

    Returns:
        dict -- A dictionary containing the status of the invocation."""
    gutenberg_id = event['gutenberg_id']

    from db import db
    with db(db_connection, False) as con:

        import epub_downloader
        f, filename = epub_downloader.download_ebook_to_temp(gutenberg_id)

        import epub_parser
        epub = epub_parser.EpubParser(filename, f)
        if(not epub.can_be_unzipped()):
            raise ValueError(
                f"can't be unzipped, invalid epub file, {filename}")

        ebook_source = con.get_book_source_by_hash(epub.file_hash)
        if(not ebook_source):
            print("Uploading to S3")
            s3_client = boto3.resource('s3')
            f.seek(0)
            config = boto3.s3.transfer.TransferConfig(multipart_threshold=262144, max_concurrency=5, multipart_chunksize=262144,
                                                      num_download_attempts=5, max_io_queue=5, io_chunksize=262144, use_threads=True)
            s3buffer = NonCloseableBufferedReader(f)
            response = s3_client.meta.client.upload_fileobj(
                s3buffer, bucket_name, filename, Config=config)
            s3buffer.detach()
            print("Uploaded")

            ebook_source_id = con.add_book_source(
                "gutenberg", filename, f"s3://{bucket_name}/{filename}", epub.file_hash)
        else:
            print("Skip Uploading")
            ebook_source_id = ebook_source[0]

        book_id = None
        if(ebook_source):
            book = con.get_book_by_ebook_source_id(ebook_source_id)
            if(book):
                book_id = book[0]

        epub.parse()
        if(not book_id):
            book_id = con.add_book(ebook_source_id, epub.title, epub.author,
                                   epub.slug, epub.description, epub.publication)

        print("Proccessing Chapters")
        con.add_chapters(book_id, epub.content.chapters)
        print("Proccessing Images")
        con.add_images(book_id, epub.content.images)
        print("Done")

        event['book_id'] = book_id
        event['ebook_source_id'] = ebook_source_id
        return {
            'statusCode': 200,
            'body': json.dumps(event)
        }


def DownloadRangeBooks(event, context):
    """Downloads a range of books, given a start and end gutenberg id. Invokes the download_book function for each book.

    Arguments:
        event {dict} -- A dictionary containing the start and end gutenberg id.
        context {object} -- The Lambda context object.

    Returns:
        dict -- A dictionary containing the status of the invocation."""
    # body = {"start": n, "end": m}

    start_id = event['start']
    end_id = event['end']

    responses = []
    client = boto3.client('lambda')

    import epub_downloader
    books = epub_downloader.get_csv_reader(False)

    for book in books:
        if(book['Type'] != 'Text'):
            continue

        book_id = int(book['Text#'])
        if(book_id >= start_id and book_id <= end_id):
            response = client.invoke(
                FunctionName='downloadBook',
                InvocationType='Event',  # 'RequestResponse',
                Payload=json.dumps({"gutenberg_id": book_id}),
            )
            print(f"Requesting book ({book_id}) download")

            del response['Payload']
            responses.append(response)

    return {
        'statusCode': 200,
        'body': json.dumps(responses),
    }


if __name__ == "__main__":
    res = DownloadBook("{\"gutenberg_id\": 1}", None)
    print(res)
    res = UpdateBook("{\"book_id\": 1, \"ebook_source_id\": 1}", None)
    print(res)
