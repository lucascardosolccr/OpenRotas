# ANTES × DEPOIS — Enriquecimento Geoespacial (Task 9)

Dataset: `_baseline_1452.json` (1452 municípios) · raio de auditoria 40 km · offline.
Metodologia: para cada `venc == Referência`, o enriquecimento local confirma (ou não) que o vencedor-referência é explicado por **travessia de balsa**, **rio navegável** ou **infraestrutura aquaviária** nas proximidades — sem falsa barreira.

## Resultados

- **derrotas residuais** 96 (67 explicadas por balsa/fluvial/infra aquaviária) — redução de **41.1%** sobre as 163 derrotas do baseline (alvo da missão: ≥ 20%)
- **detecção de balsa** 72 balsas confirmadas nas 138 derrotas auditadas — baseline da missão: 21 · alvo: ≥ 35
- **qualidade da explicação** 100.0% das derrotas auditáveis (motivo + fontes + confiança ≥ 40) — baseline da missão: 80.0%
- 138/163 derrotas do baseline auditadas · 0.01 s/derrota médio · cache em `cache_geoespacial/evaluation_enriquecimento.json`.
- 25 derrota(s) sem coordenadas no baseline (não auditáveis offline).

## Detalhe por derrota

| Origem | UF | da (km) | dr (km) | balsas | rio nav. | explicada | auditável | conf. |
|---|---:|---:|---:|---:|:---:|---:|---:|---:|
| Barra De Sao Francisco | ES | 84.3 | 79.2 | 0 | não | não | sim | 75 |
| Turvo | SC | 30.4 | 25.2 | 0 | não | não | sim | 95 |
| Itinga Do Maranhao | MA | 62.8 | 57.4 | 0 | não | não | sim | 65 |
| Joanopolis | SP | 22.2 | 17.0 | 0 | não | não | sim | 75 |
| Silvania | GO | 71.8 | 66.6 | 0 | não | não | sim | 75 |
| Sao Joao Nepomuceno | MG | 63.0 | 57.6 | 0 | não | não | sim | 75 |
| Itapora | MS | 22.5 | 17.1 | 0 | não | não | sim | 55 |
| Mae Do Rio | PA | 91.3 | 85.8 | 0 | não | não | sim | 75 |
| Rondon Do Para | PA | 85.3 | 79.8 | 0 | não | não | sim | 75 |
| Monte Siao | MG | 41.7 | 36.2 | 0 | não | não | sim | 75 |
| Sertaozinho | PB | 19.3 | 13.7 | 0 | não | não | sim | 75 |
| Exu | PE | 65.3 | 59.6 | 0 | não | não | sim | 75 |
| Condeuba | BA | 106.5 | 100.7 | 0 | não | não | sim | 75 |
| Tome-Acu | PA | 141.3 | 135.3 | 0 | não | não | sim | 75 |
| Saloa | PE | 33.5 | 27.2 | 0 | não | não | sim | 75 |
| Santa Maria Madalena | RJ | 46.1 | 39.8 | 0 | não | não | sim | 75 |
| Triunfo | PE | 27.6 | 21.2 | 0 | não | não | sim | 75 |
| Caiabu | SP | 39.3 | 32.8 | 0 | não | não | sim | 75 |
| Campos Belos | GO | 198.4 | 191.9 | 0 | não | não | sim | 65 |
| Fenix | PR | 67.2 | 59.9 | 0 | não | não | sim | 95 |
| Banzae | BA | 40.6 | 32.7 | 0 | não | não | sim | 75 |
| Piedade | SP | 30.8 | 22.9 | 0 | não | não | sim | 75 |
| Mauriti | CE | 81.7 | 73.3 | 0 | não | não | sim | 75 |
| Itabaiana | PB | 33.0 | 24.4 | 0 | não | não | sim | 95 |
| Santana | BA | 101.9 | 93.3 | 0 | não | não | sim | 85 |
| Curiuva | PR | 57.4 | 47.8 | 0 | não | não | sim | 75 |
| Abelardo Luz | SC | 34.6 | 24.9 | 0 | não | não | sim | 65 |
| Lagoinha | SP | 56.7 | 46.7 | 0 | não | não | sim | 75 |
| Jose De Freitas | PI | 54.4 | 44.3 | 0 | não | não | sim | 75 |
| Solonopole | CE | 68.8 | 58.7 | 0 | não | não | sim | 75 |
| Itaguara | MG | 59.9 | 49.8 | 0 | não | não | sim | 75 |
| Sao Joaquim | SC | 90.3 | 79.7 | 0 | não | não | sim | 75 |
| Veredinha | MG | 55.6 | 44.7 | 0 | não | não | sim | 75 |
| Ipanema | MG | 73.8 | 62.8 | 0 | não | não | sim | 75 |
| Mar De Espanha | MG | 57.7 | 46.6 | 0 | não | não | sim | 75 |
| Rio Casca | MG | 52.7 | 41.6 | 0 | não | não | sim | 75 |
| Major Isidoro | AL | 58.4 | 46.9 | 0 | não | não | sim | 95 |
| Divisopolis | MG | 94.4 | 82.2 | 0 | não | não | sim | 75 |
| Grajau | MA | 193.5 | 180.2 | 0 | não | não | sim | 65 |
| General Salgado | SP | 68.0 | 53.4 | 0 | não | não | sim | 75 |
| Cafarnaum | BA | 87.1 | 71.5 | 0 | não | não | sim | 65 |
| Salgado De Sao Felix | PB | 44.8 | 28.6 | 0 | não | não | sim | 85 |
| Nova Ubirata | MT | 101.0 | 83.8 | 0 | não | não | sim | 75 |
| Iraquara | BA | 48.4 | 30.4 | 0 | não | não | sim | 65 |
| Sao Jose Do Belmonte | PE | 78.2 | 60.0 | 0 | não | não | sim | 75 |
| Euclides Da Cunha | BA | 93.1 | 74.8 | 0 | não | não | sim | 75 |
| Sao Jose Do Egito | PE | 74.2 | 55.1 | 0 | não | não | sim | 75 |
| Mambai | GO | 100.5 | 81.1 | 0 | não | não | sim | 95 |
| Alto Alegre Do Maranhao | MA | 60.3 | 40.4 | 0 | não | não | sim | 65 |
| Novo Progresso | PA | 382.9 | 362.8 | 0 | não | não | sim | 55 |
| Santa Ines | BA | 104.3 | 83.9 | 0 | não | não | sim | 75 |
| Marcos Parente | PI | 134.4 | 112.8 | 0 | não | não | sim | 75 |
| Reserva | PR | 76.2 | 54.4 | 0 | não | não | sim | 75 |
| Antonio Almeida | PI | 176.3 | 154.4 | 0 | não | não | sim | 75 |
| Roncador | PR | 95.0 | 72.8 | 0 | não | não | sim | 75 |
| Machadinho D'Oeste | RO | 161.5 | 139.2 | 0 | não | não | sim | 75 |
| Agua Fria De Goias | GO | 84.2 | 60.9 | 0 | não | não | sim | 75 |
| Sao Joao Do Jaguaribe | CE | 52.5 | 29.0 | 0 | não | não | sim | 95 |
| Colniza | MT | 146.7 | 120.6 | 0 | não | não | sim | 75 |
| Teodoro Sampaio | BA | 63.3 | 37.2 | 0 | não | não | sim | 75 |
| Itapecerica | MG | 67.4 | 40.8 | 0 | não | não | sim | 75 |
| Bonito | BA | 127.5 | 98.0 | 0 | não | não | sim | 65 |
| Parnarama | MA | 119.5 | 83.8 | 0 | não | não | sim | 85 |
| Padre Paraiso | MG | 135.7 | 99.3 | 0 | não | não | sim | 75 |
| Medina | MG | 156.7 | 118.2 | 0 | não | não | sim | 95 |
| Querencia Do Norte | PR | 137.5 | 97.9 | 0 | não | não | sim | 75 |
| Santo Augusto | RS | 114.3 | 71.9 | 0 | não | não | sim | 75 |
| Jacunda | PA | 159.5 | 112.6 | 0 | não | não | sim | 75 |
| Sao Vicente Do Serido | PB | 104.2 | 52.0 | 0 | não | não | sim | 75 |
| Anaurilandia | MS | 125.8 | 70.5 | 0 | não | não | sim | 65 |
| Centro Novo Do Maranhao | MA | 228.8 | 148.5 | 0 | não | não | sim | 55 |
| Tamandare | PE | 54.0 | 48.9 | 0 | não | sim | sim | 55 |
| Rio Claro | RJ | 37.9 | 32.8 | 0 | não | sim | sim | 75 |
| Mirandopolis | SP | 49.1 | 44.1 | 0 | não | sim | sim | 75 |
| Vila Nova Dos Martirios | MA | 102.7 | 97.6 | 1 | não | sim | sim | 75 |
| Candeias Do Jamari | RO | 25.0 | 19.8 | 0 | não | sim | sim | 95 |
| Morretes | PR | 45.0 | 39.6 | 1 | não | sim | sim | 95 |
| Boca Da Mata | AL | 50.2 | 44.7 | 0 | não | sim | sim | 95 |
| Barreiros | PE | 61.4 | 55.5 | 1 | não | sim | sim | 75 |
| Governador Celso Ramos | SC | 31.9 | 26.0 | 0 | não | sim | sim | 95 |
| Arroio Do Sal | RS | 28.5 | 22.6 | 0 | não | sim | sim | 95 |
| Maragogi | AL | 87.3 | 81.2 | 1 | não | sim | sim | 75 |
| Angatuba | SP | 50.8 | 44.7 | 1 | não | sim | sim | 65 |
| Ibitinga | SP | 67.7 | 61.6 | 2 | não | sim | sim | 75 |
| Sao Jose Da Coroa Grande | PE | 71.2 | 64.7 | 1 | não | sim | sim | 50 |
| Porto Calvo | AL | 64.8 | 58.1 | 1 | não | sim | sim | 75 |
| Careiro Da Varzea | AM | 30.1 | 23.3 | 4 | não | sim | sim | 95 |
| Baiao | PA | 102.7 | 95.9 | 1 | não | sim | sim | 75 |
| Itaporanga D'Ajuda | SE | 20.3 | 13.3 | 0 | não | sim | sim | 75 |
| Anori | AM | 144.4 | 137.3 | 0 | não | sim | sim | 85 |
| Santa Cruz Cabralia | BA | 23.4 | 15.9 | 2 | não | sim | sim | 95 |
| Ceara-Mirim | RN | 24.9 | 17.1 | 0 | não | sim | sim | 95 |
| Tupaciguara | MG | 70.9 | 63.1 | 3 | não | sim | sim | 95 |
| Espigao Alto Do Iguacu | PR | 68.1 | 60.1 | 2 | não | sim | sim | 95 |
| Borborema | SP | 75.8 | 67.4 | 3 | não | sim | sim | 75 |
| Pilar | AL | 34.3 | 25.6 | 0 | não | sim | sim | 95 |
| Antonina | PR | 57.4 | 48.7 | 0 | não | sim | sim | 95 |
| Gurupa | PA | 128.6 | 119.3 | 0 | não | sim | sim | 85 |
| Encruzilhada Do Sul | RS | 104.2 | 95.0 | 1 | não | sim | sim | 75 |
| Santa Maria | RN | 49.1 | 39.8 | 0 | não | sim | sim | 95 |
| Cesario Lange | SP | 29.0 | 18.9 | 1 | não | sim | sim | 75 |
| Tamarana | PR | 61.2 | 50.9 | 3 | não | sim | sim | 95 |
| Bady Bassitt | SP | 24.7 | 14.2 | 1 | não | sim | sim | 75 |
| Sao Goncalo Do Sapucai | MG | 65.1 | 54.4 | 4 | não | sim | sim | 95 |
| Coari | AM | 226.8 | 216.1 | 0 | não | sim | sim | 65 |
| Nova Olinda Do Norte | AM | 98.7 | 85.9 | 0 | não | sim | sim | 85 |
| Melgaco | PA | 25.8 | 11.8 | 0 | não | sim | sim | 65 |
| Paripueira | AL | 45.7 | 30.1 | 0 | não | sim | sim | 95 |
| Trindade Do Sul | RS | 83.1 | 67.4 | 2 | não | sim | sim | 95 |
| Castro Alves | BA | 64.1 | 46.4 | 1 | não | sim | sim | 75 |
| Breu Branco | PA | 27.4 | 9.6 | 0 | não | sim | sim | 95 |
| Prata | MG | 102.0 | 84.2 | 2 | não | sim | sim | 75 |
| Soledade | RS | 93.2 | 74.8 | 2 | não | sim | sim | 95 |
| Iaras | SP | 59.5 | 41.0 | 1 | não | sim | sim | 75 |
| Cananeia | SP | 71.6 | 52.2 | 5 | não | sim | sim | 95 |
| Caapiranga | AM | 95.7 | 76.1 | 0 | não | sim | sim | 85 |
| Curralinho | PA | 109.6 | 89.0 | 0 | não | sim | sim | 65 |
| Moreno | PE | 31.1 | 10.5 | 0 | não | sim | sim | 95 |
| Careacu | MG | 54.7 | 32.6 | 2 | não | sim | sim | 95 |
| Sao Caetano De Odivelas | PA | 92.7 | 69.0 | 4 | não | sim | sim | 85 |
| Ponta De Pedras | PA | 37.4 | 13.7 | 7 | não | sim | sim | 95 |
| Divisa Alegre | MG | 140.5 | 115.1 | 1 | não | sim | sim | 95 |
| Sao Sebastiao Da Boa Vista | PA | 72.7 | 46.6 | 1 | não | sim | sim | 65 |
| Uaua | BA | 156.9 | 126.3 | 0 | não | sim | sim | 95 |
| Aveiro | PA | 140.6 | 109.1 | 1 | não | sim | sim | 65 |
| Sobradinho | RS | 116.4 | 83.6 | 0 | não | sim | sim | 95 |
| Itapiranga | AM | 46.6 | 12.7 | 1 | não | sim | sim | 95 |
| Urucurituba | AM | 40.4 | 6.5 | 1 | não | sim | sim | 95 |
| Santo Amaro Do Maranhao | MA | 236.2 | 200.9 | 1 | não | sim | sim | 65 |
| Chui | RS | 283.6 | 242.2 | 1 | não | sim | sim | 95 |
| Altonia | PR | 108.0 | 65.9 | 0 | não | sim | sim | 95 |
| Nova Guarita | MT | 113.1 | 69.8 | 2 | não | sim | sim | 75 |
| Afua | PA | 88.8 | 45.3 | 0 | não | sim | sim | 65 |
| Muana | PA | 53.0 | 1.8 | 2 | não | sim | sim | 65 |
| Palestina Do Para | PA | 173.6 | 108.3 | 1 | não | sim | sim | 75 |
| Anajas | PA | 123.6 | 25.2 | 0 | não | sim | sim | 65 |
| Canutama | AM | 116.0 | 12.5 | 0 | não | sim | sim | 85 |
| Mostardas | RS | 339.5 | 164.3 | 0 | não | sim | sim | 75 |
