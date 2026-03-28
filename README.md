# Pinterest Web Scraper

Scraper funcional para Pinterest com rolagem automática e exportação em JSON.

## Recursos

- Coleta pins em páginas de busca, perfil ou board.
- Rolagem automática até atingir `--max-pins`.
- Exporta: `pin_id`, `pin_url`, `image_url`, `title`, `description`, `source_url`.
- Modo opcional de enriquecimento (`--enrich-details`) abrindo cada pin.

## Requisitos

- Python 3.10+
- Dependências:

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## Uso

```bash
python pinterest_scraper.py \
  --url "https://www.pinterest.com/search/pins/?q=decoração" \
  --max-pins 80 \
  --output pins.json
```

### Opções úteis

- `--enrich-details`: coleta metadados extras de cada pin (mais lento).
- `--headed`: abre navegador visível para debug.
- `--timeout`: limite máximo de execução em segundos.

## Exemplo de saída

```json
{
  "source_url": "https://www.pinterest.com/search/pins/?q=decoração",
  "total": 2,
  "pins": [
    {
      "pin_id": "1234567890",
      "pin_url": "https://www.pinterest.com/pin/1234567890/",
      "image_url": "https://i.pinimg.com/originals/...jpg",
      "title": "Ideia de decoração",
      "description": "Sala minimalista",
      "source_url": "https://example.com/post"
    }
  ]
}
```

## Observações

- Pinterest pode alterar o HTML e exigir ajustes de seletores no futuro.
- Respeite os Termos de Uso, robots e limites de requisição.
