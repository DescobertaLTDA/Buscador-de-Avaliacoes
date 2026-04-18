# Voxly

Buscador de avaliacoes para apps da Google Play.

O Voxly transforma reviews em sinais de produto: sentimento, notas, temas recorrentes, comentarios relevantes, criticas recentes, comparativo entre apps e exportacao em CSV.

## Rodar localmente

```bash
pip install -r requirements.txt
python server.py
```

Depois acesse:

```text
http://localhost:5000
```

## Publicar na Vercel

Este projeto usa Flask com Python Runtime da Vercel.

Ao importar o repositorio na Vercel, mantenha a deteccao automatica ou selecione Other. A Vercel usa o `server.py` como entrada Flask e instala as dependencias do `requirements.txt`.
