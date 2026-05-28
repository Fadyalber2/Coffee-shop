from app import app, basedir, db, ensure_schema_updates, seed_sample_data
import os


with app.app_context():
    os.makedirs(os.path.join(basedir, "instance"), exist_ok=True)
    db.create_all()
    ensure_schema_updates()
    seed_sample_data()

