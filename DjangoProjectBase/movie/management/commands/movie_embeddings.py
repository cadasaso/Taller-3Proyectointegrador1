import os
import numpy as np
from django.core.management.base import BaseCommand
from movie.models import Movie
from openai import OpenAI
from dotenv import load_dotenv

class Command(BaseCommand):
    help = "Generate and store embeddings for all movies in the database"

    # ➕ Añadido: opciones para mostrar un embedding al final
    def add_arguments(self, parser):
        parser.add_argument("--show-random", action="store_true", help="Muestra un embedding al azar al finalizar")
        parser.add_argument("--title", type=str, help="Muestra el embedding de este título (si existe)")
        parser.add_argument("--n", type=int, default=8, help="Cuántos valores del vector imprimir (default: 8)")

    def handle(self, *args, **kwargs):
        # ✅ Load OpenAI API key
        load_dotenv('openAI.env')
        client = OpenAI(api_key=os.environ.get('openia_apikey'))

        # ✅ Fetch all movies from the database
        movies = Movie.objects.all()
        self.stdout.write(f"Found {movies.count()} movies in the database")

        def get_embedding(text):
            response = client.embeddings.create(
                input=[text],
                model="text-embedding-3-small"
            )
            return np.array(response.data[0].embedding, dtype=np.float32)

        # ✅ Iterate through movies and generate embeddings
        for movie in movies:
            try:
                emb = get_embedding(movie.description)
                # ✅ Store embedding as binary in the database
                movie.emb = emb.tobytes()
                movie.save()
                self.stdout.write(self.style.SUCCESS(f"✅ Embedding stored for: {movie.title}"))
            except Exception as e:
                self.stderr.write(f"❌ Failed to generate embedding for {movie.title}: {e}")

        self.stdout.write(self.style.SUCCESS("🎯 Finished generating embeddings for all movies"))

        # ➕ Añadido: Mostrar embedding al azar o por título (según flags)
        title = kwargs.get("title")
        show_random = kwargs.get("show_random")
        n = max(1, kwargs.get("n") or 8)

        if title or show_random:
            qs = Movie.objects.exclude(emb__isnull=True).exclude(emb=b'')
            if title:
                movie = qs.filter(title=title).first()
                if not movie:
                    self.stderr.write(f"❌ No se encontró la película (o sin embedding): {title}")
                    return
            else:
                movie = qs.order_by("?").first()
                if not movie:
                    self.stderr.write("⚠️ No hay embeddings guardados aún para mostrar.")
                    return

            vec = np.frombuffer(movie.emb, dtype=np.float32)
            self.stdout.write(self.style.MIGRATE_HEADING(f"Pelicula: {movie.title}"))
            self.stdout.write(f"Dimensión del embedding: {vec.shape}")
            self.stdout.write(f"Primeros {n} valores: {vec[:n]}")
