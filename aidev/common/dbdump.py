import sqlite3
from typing import Tuple, Iterable


class DatabaseDumper:
    def __init__(self, sqlite_db_path):
        self.sqlite_db_path = sqlite_db_path

    def get_column_names(self, table_name: str) -> Tuple[str]:
        connection = sqlite3.connect(self.sqlite_db_path)
        cursor = connection.cursor()
        cursor.execute(f"PRAGMA table_info('{table_name}');")
        columns = tuple(info[1] for info in cursor.fetchall())
        connection.close()
        return columns

    def iter_rows(self, table_name: str) -> Iterable[Tuple[str]]:
        connection = sqlite3.connect(self.sqlite_db_path)
        cursor = connection.cursor()
        cursor.execute(f'SELECT * FROM "{table_name}" ORDER BY "Id"')
        for row in cursor:
            yield row
        connection.close()


def test():
    dumper = DatabaseDumper(r'C:\Dev\AI\Coding\example-shop\Shop.Web\FoodShop.Dev.db')
    table_name = 'Foods'
    print(dumper.get_column_names(table_name))
    for row in dumper.iter_rows(table_name):
        print(row)


if __name__ == '__main__':
    test()
