var express = require("express")
var router = express.Router()
var { Client, Pool } = require("pg")

if (process.env.DATABASE_URL) {
  var pool = new Client(process.env.DATABASE_URL)
  pool.connect()
} else {
  var pool = new Pool()
}

router.get("/get/:title", function (req, res, next) {
  pool.query(
    `SELECT * FROM books WHERE slug = $1`,
    [req.params.title],
    (err, result) => {
      const book = result.rows[0]
      pool.query(
        `SELECT id, book_id, title, slug FROM chapters WHERE book_id = $1`,
        [book.id],
        (err, result) => {
          const chapters = result.rows
          book.chapters = chapters
          res.json(book)
        }
      )
    }
  )
})

router.get("/chapter/:id", function (req, res, next) {
  pool.query(
    `SELECT * FROM chapters WHERE id = $1`,
    [req.params.id],
    (err, result) => {
      const chapter = result.rows[0]
      res.json(chapter)
    }
  )
})

router.get("/catalog", function (req, res, next) {
  pool.query("SELECT * FROM books", (err, result) => {
    const books = result.rows
    res.json(books)
  })
})

router.get("/search/:query", function (req, res, next) {
  pool.query(
    `SELECT * FROM books WHERE title LIKE ('%' || ($1) || '%')`,
    [req.params.query],
    (err, result) => {
      const books = result.rows
      res.json(books)
    }
  )
})
module.exports = router
