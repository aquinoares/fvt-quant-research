# Painel de sinais ao vivo A/B

O painel usa o feed público spot BTCUSDT da Binance: REST para carregar candles de 4h e WebSocket para receber preço e atualizações em tempo real. Não usa chave de conta, não lê saldo privado e não envia ordens.

## Motores exibidos

- **A — SMA-20 4h:** replica a regra pedagógica existente em \`learning/experiments/backtest.py\`. A posição alvo é comprada quando o último fechamento conhecido fica acima da média dos 20 fechamentos anteriores.
- **B — P6-MOM 4h:** reproduz a regra existente com ROC de 96 candles acima de 0,5%, long-only, conforme \`research/mom_tf240.py\`. O arquivo de estratégia e o workflow de coleta não são alterados por esta implementação.
- Os eventos são considerados na abertura do candle seguinte ao cálculo. Um EXIT fecha a operação simulada e recebe WIN/LOSS/FLAT conforme o retorno estimado após custos de 15 bps por lado.

## O que os números significam

A linha principal de sinais/WIN/LOSS é a simulação histórica executada sobre candles públicos já carregados, e é recalculada quando entram novos candles. A linha “Ao vivo neste navegador” registra apenas eventos novos observados depois da conexão WebSocket nesta sessão, com persistência no localStorage do navegador. Os números não são ordens executadas nem resultado de uma conta de corretora.

O histórico local de candles e os contadores ao vivo não sincronizam entre navegadores/dispositivos. Para persistência central do robô mesmo com a página fechada, é necessário um serviço servidor/armazenamento conectado; esta versão não declara existir tal serviço. Lacunas de candles são mostradas e as regras não geram novos alvos quando o trecho necessário não é contínuo.

## Fonte e manutenção

A implementação vive em \`dashboard/live-signals.js\` e possui testes em \`tests/dashboard/live-signals.test.cjs\`. A página do dashboard deve copiar o arquivo JS para o diretório publicado ao construir o artefato.