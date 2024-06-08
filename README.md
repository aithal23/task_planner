# Task Planner telegram bot

* You can run this as Docker container or locally by installing the pip modules `pip install -r requirements.txt` and `python telegram_bot.py`

## Configs

### db_config.json
* MySQL config ; database, host, username and password
* Can connect to Maria DB as well.
* After creating the database in MySQL, run the following ;
```
CREATE DATABASE telegram_bot;
USE telegram_bot;
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    telegram_id BIGINT NOT NULL UNIQUE,
    username VARCHAR(255),
    is_authorized BOOLEAN DEFAULT FALSE,
    is_admin BOOLEAN DEFAULT FALSE
);
CREATE TABLE tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    tasks TEXT,
    task_date DATE,
    FOREIGN KEY (user_id) REFERENCES users(telegram_id)
);
# OPTIONAL
INSERT INTO users (telegram_id, username, is_authorized, is_admin) VALUES (<ADMIN_USER_ID>, '<ADMIN_USERNAME>', TRUE, TRUE);
```

### .env
* Set the ADMIN_USER_ID with your telegram user ID
* Set the BOT_TOKEN with your telegram bot token
```
BOT_TOKEN=123:aaa_ss
ADMIN_USER_ID=42069
```
