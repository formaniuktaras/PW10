# InventoryLite

Мінімалістична локальна програма для обліку довідників брендів, категорій і товарів.

## Як зібрати

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

або у cmd:

```bat
build.bat
```

Під час збірки іконка автоматично генерується з base64 (`icons/app_ico_base64.txt`) у `icons/app.ico`, тому двійкових файлів у репозиторії немає.

## Як запустити

Після збірки відкрийте `dist\InventoryLite.exe` (one-file, без консолі).

## Дані

База даних та журнали: `%LOCALAPPDATA%\InventoryLite\` (`data.db`, `app.log`, резервні копії, CSV-експорти).

## Можливості

- CRUD для Brands, Categories, Products з пошуком по SKU/назві.
- Експорт таблиць у CSV.
- Резервна копія БД через меню Файл.
- Перевірка унікальності SKU та назв, дружні повідомлення про помилки.
- Блокування другої копії додатку.
