import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import logging

# попытка импортировать pandas (необязательно)
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except Exception:
    pd = None
    PANDAS_AVAILABLE = False

logger = logging.getLogger(__name__)


class GoogleSheetsClient:
    def __init__(self, service_file: str, sheet_id: str):
        """Подключение к Google Sheets (лист Complaints)"""
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(service_file, scopes=scopes)
        self.client = gspread.authorize(creds)
        self.sheet = self.client.open_by_key(sheet_id).worksheet("Complaints")

        # Проверяем и корректируем заголовки (best-effort)
        try:
            self.ensure_headers()
        except Exception as e:
            logger.warning(f"ensure_headers failed: {e}")

    # ======================================================
    # Проверка и выравнивание заголовков (без удаления строки)
    # ======================================================
    def ensure_headers(self):
        expected_headers = [
            "ID", "Дата", "Филиал", "Родитель", "Ученик", "Телефон", "Категория", "Жалоба",
            "Статус", "Время обзвона", "Решение", "Ответственный",
            "Время решения", "Время уведомления", "Кто уведомил родителя",
            "Отправитель", "User ID"
        ]

        current_headers = self.sheet.row_values(1)
        # Нормализуем: обрезаем пробелы
        current_headers = [c.strip() for c in current_headers]

        if current_headers != expected_headers:
            logger.info("Заголовки не совпадают — заменяю первую строку на ожидаемые заголовки.")
            # Обновляем первую строку (без удаления)
            # gspread: update accepts A1 range and 2D list
            try:
                self.sheet.update("A1", [expected_headers], value_input_option="USER_ENTERED")
                logger.info("Заголовки синхронизированы.")
            except Exception as e:
                logger.error(f"Не удалось обновить заголовки: {e}")
                raise

    # ======================================================
    # Добавление жалобы (строго по колонкам)
    # ======================================================
    def add_complaint(self, complaint: dict):
        headers = self.sheet.row_values(1)
        if not headers:
            logger.error("Нет заголовков в листе — add_complaint прерван.")
            return False
        try:
            row = [complaint.get(h, "") for h in headers]
            self.sheet.append_row(row, value_input_option="USER_ENTERED")
            logger.info(f"Добавлена жалоба ID: {complaint.get('ID', '?')}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при добавлении жалобы: {e}")
            return False

    # ======================================================
    # Поиск по ID
    # ======================================================
    def get_row_by_id(self, complaint_id: str):
        """Возвращает (индекс строки, словарь данных) по ID; безопасно (не использует get_all_records)"""
        try:
            all_values = self.sheet.get_all_values()
            if not all_values:
                return None, {}

            headers = all_values[0]
            for i, row in enumerate(all_values[1:], start=2):
                # пропускаем пустые строки
                if not row or len(row) == 0:
                    continue
                # предполагаем, что ID в первой колонке
                cell_id = str(row[0]).strip() if len(row) >= 1 else ""
                if cell_id == str(complaint_id).strip():
                    data = {headers[j]: (row[j] if j < len(row) else "") for j in range(len(headers))}
                    return i, data
            return None, {}
        except Exception as e:
            logger.error(f"Ошибка при поиске ID {complaint_id}: {e}")
            return None, {}

    # ======================================================
    # Обновление по ID (batch update)
    # ======================================================
    def update_by_id(self, complaint_id: str, updates: dict):
        """Обновляет значения по ID (все ключи должны совпадать с заголовками)"""
        try:
            row_index, _ = self.get_row_by_id(complaint_id)
            if not row_index:
                logger.warning(f"Жалоба с ID {complaint_id} не найдена.")
                return False

            headers = self.sheet.row_values(1)
            if not headers:
                logger.error("Нет заголовков в таблице.")
                return False

            # диапазон от 1 до len(headers) в строке row_index
            cell_list = self.sheet.range(row_index, 1, row_index, len(headers))
            for cell in cell_list:
                header = headers[cell.col - 1]
                if header in updates:
                    cell.value = updates[header]

            # batch update
            self.sheet.update_cells(cell_list, value_input_option="USER_ENTERED")
            logger.info(f"Жалоба {complaint_id} успешно обновлена.")
            return True

        except Exception as e:
            logger.error(f"Ошибка при обновлении жалобы {complaint_id}: {e}")
            return False

    # ======================================================
    # Получение всех данных (fallback: с pandas/без pandas)
    # ======================================================
    def get_all_data(self):
        """Возвращает все строки таблицы. Если pandas доступна — DataFrame, иначе — список dict'ов."""
        try:
            data = self.sheet.get_all_values()
            if not data or len(data) < 1:
                return pd.DataFrame() if PANDAS_AVAILABLE else []

            headers = data[0]
            rows = data[1:]

            if PANDAS_AVAILABLE:
                df = pd.DataFrame(rows, columns=headers)
                return df
            else:
                result = []
                for r in rows:
                    d = {}
                    for i, h in enumerate(headers):
                        d[h] = r[i] if i < len(r) else ""
                    result.append(d)
                return result
        except Exception as e:
            logger.error(f"Ошибка при получении всех данных: {e}")
            return pd.DataFrame() if PANDAS_AVAILABLE else []

    # ======================================================
    # Фильтрация по диапазону дат (строки или DataFrame)
    # ======================================================
    def get_by_date_range(self, start_date: str, end_date: str):
        """start_date, end_date — в формате 'YYYY-MM-DD' или datetime-строки; возвращает список словарей"""
        # если pandas доступна и ты хочешь DataFrame — можно вернуть df; но здесь возвращаем список dict
        data = self.get_all_data()
        out = []
        try:
            # если pandas
            if PANDAS_AVAILABLE and isinstance(data, pd.DataFrame):
                df = data.copy()
                df["Дата"] = pd.to_datetime(df["Дата"], errors="coerce", format="%d.%m.%Y %H:%M")
                mask = (df["Дата"] >= pd.to_datetime(start_date)) & (df["Дата"] <= pd.to_datetime(end_date))
                df2 = df.loc[mask]
                return df2.to_dict(orient="records")
            else:
                # data — список словарей
                from datetime import datetime as dt
                s = dt.fromisoformat(start_date) if isinstance(start_date, str) and "T" in start_date else dt.fromisoformat(start_date)
                e = dt.fromisoformat(end_date) if isinstance(end_date, str) and "T" in end_date else dt.fromisoformat(end_date)
                for r in data:
                    try:
                        dt_val = datetime.strptime(r.get("Дата", ""), "%d.%m.%Y %H:%M")
                    except Exception:
                        continue
                    if s <= dt_val <= e:
                        out.append(r)
                return out
        except Exception as exc:
            logger.error(f"Ошибка фильтрации по датам: {exc}")
            return out
