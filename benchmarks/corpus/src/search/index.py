"""Full-text search over task titles and notes, inside PostgreSQL."""

QUERY = """
SELECT id, title
FROM tasks
WHERE search_doc @@ websearch_to_tsquery('english', %s)
ORDER BY ts_rank(search_doc, websearch_to_tsquery('english', %s)) DESC
LIMIT 20
"""

MIGRATION = """
ALTER TABLE tasks ADD COLUMN search_doc tsvector
  GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || coalesce(notes, ''))) STORED;
CREATE INDEX tasks_search_doc ON tasks USING gin (search_doc);
"""
