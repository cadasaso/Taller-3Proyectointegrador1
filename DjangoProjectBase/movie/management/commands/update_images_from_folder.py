# movie/management/commands/update_images_from_folder.py
from pathlib import Path
import re
import unicodedata

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.apps import apps

MODEL_PATH = "movie.Movie"      # app.Model
IMAGE_FIELD = "image"           # nombre del ImageField
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")

def normalize_raw(s: str) -> str:
    """
    Normalización mínima para comparar 'tal como están':
    - NFKC (acentos intactos, forma consistente)
    - minúsculas
    - guion bajo -> espacio
    - comillas tipográficas -> comilla simple
    - colapsar espacios
    - quitar prefijo 'm ' o 'm_' opcionalmente se maneja aparte
    """
    s = unicodedata.normalize("NFKC", str(s)).lower()
    s = s.replace("_", " ")
    s = s.replace("’", "'").replace("`", "'")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def strip_m_prefix(s: str) -> str:
    # quita "m " o "m_" o "m-" al inicio (insensible a mayúsculas)
    return re.sub(r"^m[\s_\-]+", "", s, flags=re.IGNORECASE)

class Command(BaseCommand):
    help = "Asigna imágenes a Movie usando el nombre de archivo tal como está en MEDIA_ROOT/movie/images"

    def add_arguments(self, parser):
        parser.add_argument("--folder", type=str, default=str(Path("movie") / "images"))
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--overwrite", action="store_true")
        parser.add_argument("--debug", action="store_true")

    def handle(self, *args, **options):
        Movie = apps.get_model(MODEL_PATH)

        media_root = Path(settings.MEDIA_ROOT or ".").resolve()
        folder_rel = Path(options["folder"])
        images_dir = (media_root / folder_rel).resolve()
        if not images_dir.exists():
            raise CommandError(f"La carpeta no existe: {images_dir}")

        dry = options["dry_run"]
        overwrite = options["overwrite"]
        debug = options["debug"]

        # Indexa archivos por:
        # - nombre normalizado completo (p.ej. "m la captura")
        # - nombre sin prefijo m (p.ej. "la captura")
        file_index = {}
        for p in images_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                stem_norm = normalize_raw(p.stem)
                no_m_norm = normalize_raw(strip_m_prefix(p.stem))
                file_index.setdefault(stem_norm, p)
                file_index.setdefault(no_m_norm, p)

        if debug:
            self.stdout.write(self.style.MIGRATE_HEADING(f"Carpeta: {images_dir}"))
            self.stdout.write(self.style.NOTICE(f"Indexados: {len({id(v) for v in file_index.values()})} archivos (claves: {len(file_index)})"))

        updated = skipped = missing = 0

        for movie in Movie.objects.all().iterator():
            title = getattr(movie, "title", str(movie.pk))
            t_norm = normalize_raw(title)
            candidates = [
                t_norm,
                normalize_raw("m " + title),   # por si el archivo tiene prefijo m_
            ]

            match = None
            for cand in candidates:
                if cand in file_index:
                    match = file_index[cand]
                    break

            img_field = getattr(movie, IMAGE_FIELD, None)

            if not match:
                missing += 1
                self.stdout.write(f"[missing] {title}")
                if debug:
                    self.stdout.write(f"  -> claves probadas: {candidates}")
                continue

            if img_field and getattr(img_field, "name", "") and not overwrite:
                skipped += 1
                if debug:
                    self.stdout.write(f"[skip] {title} (ya tiene: {img_field.name})")
                continue

            rel_path = folder_rel / match.name

            if dry:
                self.stdout.write(f"[dry] {title} <- {rel_path}")
                updated += 1
                continue

            setattr(movie, IMAGE_FIELD, str(rel_path).replace("\\", "/"))
            movie.save(update_fields=[IMAGE_FIELD])
            updated += 1
            self.stdout.write(f"[ok] {title} <- {rel_path}")

        self.stdout.write(f"Actualizadas: {updated}\nSaltadas: {skipped}\nSin archivo: {missing}")
