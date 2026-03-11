from sqlalchemy import create_engine, select
from app.models.database import File
from app.config import get_settings
settings = get_settings()
engine = create_engine(settings.database_url_sync)
from sqlalchemy.orm import sessionmaker
Session = sessionmaker(bind=engine)
session = Session()
files = session.execute(select(File)).scalars().all()
for f in files:
    print(f.id, f.original_filename)
