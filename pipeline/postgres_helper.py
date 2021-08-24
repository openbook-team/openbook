import psycopg2

from helpers import join_path

class postgres_helper(object):

    def __init__(self, dsn):
        # dsn = "user={} password={} host={} port={} dbname={} sslmode=require"
        self.con = psycopg2.connect(dsn)
        self._create_tables()


    def _create_tables(self):
        cur = self.con.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS books (
                id SERIAL PRIMARY KEY,
                title text NOT NULL,
                author text,
                slug text,
                description text
            )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS chapters (
            id SERIAL PRIMARY KEY,
            book_id integer NOT NULL,
            title text,
            location text,
            FOREIGN KEY (book_id) REFERENCES books (id)
        )''')
        self.con.commit()

    def drop_tables(self):
        cur = self.con.cursor()
        for table_name in ['chapters', 'books']:
            cur.execute(f"DROP TABLE IF EXISTS {table_name};")
        self.con.commit()

    def add_book(self, title, author, slug, description):
        cur = self.con.cursor()
        cur.execute(
            '''INSERT INTO books (title, author, slug, description) VALUES (%s, %s, %s, %s) RETURNING id''', (title, author, slug, description))
        self.con.commit()
        return cur.fetchone()[0]


    def add_chapters(self, book_id, chapters, slug):
        cur = self.con.cursor()
        for _, title, location, _ in chapters:
            cur.execute(
                '''INSERT INTO chapters (book_id, title, location) VALUES (%s, %s, %s)''', (book_id, title, join_path(slug, location)))
        self.con.commit()