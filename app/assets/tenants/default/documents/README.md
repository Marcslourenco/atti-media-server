# Documentos por tenant

A pasta `app/assets/tenants/` separa os documentos de cada cliente (tenant), evitando mistura de catálogos e materiais entre empresas.

## Estrutura

Cada tenant possui três áreas:

- `documents/catalogs/`: catálogos comerciais versionados, como `Catalogo_Humanos_Digitais_2026_v1.pdf`.
- `documents/manuals/`: manuais, guias operacionais e materiais de treinamento.
- `documents/invoices/`: documentos fiscais e faturas, quando aplicável.

Exemplo:

```text
app/assets/tenants/{tenant_id}/documents/
├── catalogs/
├── manuals/
└── invoices/
```

## Como adicionar documentos

Crie ou utilize o diretório do tenant e coloque o arquivo na categoria correspondente. Para catálogos públicos enviados pela Meta Cloud API, configure `CATALOG_PDF_URL` com a URL pública do PDF. A URL pode apontar para GitHub Raw hoje e ser migrada para Cloudflare R2 ou Amazon S3 no futuro.

Exemplo de variável:

```text
CATALOG_PDF_URL=https://raw.githubusercontent.com/[usuario]/[repo]/main/app/assets/tenants/default/documents/catalogs/Catalogo_Humanos_Digitais_2026_v1.pdf
```

## Versionamento

Não substitua silenciosamente um catálogo publicado. Use sufixos incrementais (`v1`, `v2`, `v3`) e atualize a variável de ambiente para apontar para a versão vigente. Mantenha versões anteriores quando forem necessárias para auditoria ou rollback.

## Multi-tenant

Cada tenant deve ter seu próprio `tenant_id` e sua própria árvore de documentos. O tenant `default` usa `CATALOG_PDF_URL`; tenants adicionais podem usar uma URL pública configurada por CDN ou storage futuro. O upload automatizado via API pode ser adicionado posteriormente, mantendo a separação por tenant.
