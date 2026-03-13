import argparse
import sys

import bcrypt
import pymysql
from pymysql.cursors import DictCursor


def get_connection(host: str, user: str, password: str, database: str, port: int):
    return pymysql.connect(
        host=host,
        user=user,
        password=password,
        database=database,
        port=port,
        cursorclass=DictCursor,
        autocommit=False,
    )


def migrate_passwords(connection):
    updated = 0
    skipped = 0

    with connection.cursor() as cur:
        cur.execute("SELECT Artist_ID, Password FROM artist_table")
        rows = cur.fetchall()

        for row in rows:
            artist_id = row.get("Artist_ID")
            current_password = row.get("Password")

            if not current_password:
                skipped += 1
                continue

            if str(current_password).startswith("$2b$"):
                skipped += 1
                continue

            hashed = bcrypt.hashpw(
                str(current_password).encode("utf-8"),
                bcrypt.gensalt(),
            ).decode("utf-8")

            cur.execute(
                "UPDATE artist_table SET Password = %s WHERE Artist_ID = %s",
                (hashed, artist_id),
            )
            updated += 1

    connection.commit()
    return updated, skipped


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert plaintext passwords in artist_table to bcrypt hashes."
    )
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="Adhya@123")
    parser.add_argument("--database", default="creovibe_db")
    parser.add_argument("--port", type=int, default=3306)
    return parser.parse_args()


def main():
    args = parse_args()
    connection = None

    try:
        connection = get_connection(
            host=args.host,
            user=args.user,
            password=args.password,
            database=args.database,
            port=args.port,
        )
        updated, skipped = migrate_passwords(connection)
        print(f"Migration complete. Updated: {updated}, Skipped: {skipped}")
    except Exception as exc:
        if connection:
            connection.rollback()
        print(f"Migration failed: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        if connection:
            connection.close()


if __name__ == "__main__":
    main()
