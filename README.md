# Notícias em Foco

Portal estático em português para GitHub Pages. Exibe manchetes e resumos curtos dos feeds RSS públicos da Agência Brasil/EBC, com editoria, horário, atribuição e link para cada publicação original.

## Atualização e publicação

- O GitHub Actions atualiza o arquivo público de notícias e publica o site diariamente às 8h no fuso `America/Campo_Grande`.
- O workflow também publica novamente quando houver alterações no branch `main` e pode ser executado manualmente pela aba Actions.
- Enquanto a página está aberta, ela consulta novamente o arquivo de notícias a cada 30 minutos.
- Se as fontes não responderem, a página avisa que as notícias estão indisponíveis e não mostra manchetes fictícias.
- O portal reproduz títulos e resumos curtos do RSS; a leitura integral permanece no site original da Agência Brasil.

## Fontes

Os feeds são disponibilizados pela Agência Brasil/EBC nas editorias Geral, Internacional, Economia, Política, Saúde, Educação e Esportes. A lista oficial está em <https://agenciabrasil.ebc.com.br/feed/>.

## Arquivos

- `index.html`: layout responsivo e interface de notícias.
- `scripts/fetch_news.py`: consulta RSS, valida links da fonte e gera o JSON diário.
- `.github/workflows/pages.yml`: atualiza o feed e implanta o site no GitHub Pages.
