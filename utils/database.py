
import aiosqlite
import config


async def init_db():
    async with aiosqlite.connect(config.DATABASE) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id INTEGER PRIMARY KEY,
                log_channel INTEGER,
                welcome_channel INTEGER,
                welcome_message TEXT,
                autorole INTEGER,
                staff_role INTEGER,
                ticket_category INTEGER,
                level_channel INTEGER
            );

            CREATE TABLE IF NOT EXISTS queues (
                user_id INTEGER PRIMARY KEY,
                guild_id INTEGER,
                mode TEXT,
                ranked INTEGER,
                rank_or_level TEXT,
                joined_at REAL,
                type TEXT DEFAULT 'normal'
            );

            CREATE TABLE IF NOT EXISTS active_teams (
                team_id TEXT PRIMARY KEY,
                guild_id INTEGER,
                thread_id INTEGER,
                voice_id INTEGER,
                mode TEXT,
                members TEXT,
                created_at REAL
            );

            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT,
                guild_id INTEGER,
                user_id INTEGER,
                moderator_id INTEGER,
                reason TEXT,
                timestamp REAL
            );

            CREATE TABLE IF NOT EXISTS staff_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                user_id INTEGER,
                moderator_id INTEGER,
                note TEXT,
                timestamp REAL
            );

            CREATE TABLE IF NOT EXISTS levels (
                guild_id INTEGER,
                user_id INTEGER,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0,
                messages INTEGER DEFAULT 0,
                voice_time INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS invite_joins (
                guild_id INTEGER,
                user_id INTEGER,
                inviter_id INTEGER,
                timestamp REAL,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS tickets (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER,
                user_id INTEGER,
                category TEXT,
                claimed_by INTEGER,
                created_at REAL,
                closed INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT UNIQUE,
                guild_id INTEGER,
                user_id INTEGER,
                moderator_id INTEGER,
                action TEXT,
                reason TEXT,
                timestamp REAL
            );

            CREATE TABLE IF NOT EXISTS staff_role_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                division TEXT NOT NULL,
                role_key TEXT NOT NULL,
                role_id INTEGER NOT NULL,
                UNIQUE(guild_id, division, role_key)
            );

            CREATE TABLE IF NOT EXISTS staff_requests (
                request_id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                requester_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                division TEXT NOT NULL,
                action TEXT NOT NULL,
                old_role_id INTEGER,
                new_role_id INTEGER,
                reason TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at REAL NOT NULL,
                reviewed_at REAL,
                reviewed_by INTEGER,
                review_reason TEXT
            );

            CREATE TABLE IF NOT EXISTS staff_strikes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                issued_by INTEGER NOT NULL,
                request_id TEXT,
                reason TEXT NOT NULL,
                timestamp REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS division_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                added_by INTEGER NOT NULL,
                division TEXT NOT NULL,
                note TEXT NOT NULL,
                timestamp REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS member_stats (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                teams_created INTEGER DEFAULT 0,
                teams_joined INTEGER DEFAULT 0,
                tickets_handled INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS division_panels (
                guild_id INTEGER NOT NULL,
                division TEXT NOT NULL,
                channel_id INTEGER,
                message_id INTEGER,
                PRIMARY KEY (guild_id, division)
            );
        """)

        await db.commit()


async def get_config(guild_id: int):
    async with aiosqlite.connect(config.DATABASE) as db:
        async with db.execute(
            "SELECT * FROM guild_config WHERE guild_id = ?",
            (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

            if not row:
                await db.execute(
                    "INSERT INTO guild_config (guild_id) VALUES (?)",
                    (guild_id,)
                )
                await db.commit()
                return await get_config(guild_id)

            return row
