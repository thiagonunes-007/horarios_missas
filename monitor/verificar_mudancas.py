#!/usr/bin/env python3
"""
Verifica as páginas de horários de missa do site oficial da Arquidiocese de
Natal e envia um e-mail de alerta quando o conteúdo muda em relação à
última checagem.

Duas fontes são conferidas:
1. PAGINAS: as 4 páginas-resumo "Horários de Missa" (só a igreja matriz de
   cada paróquia, sem capelas).
2. PAGINAS_MATRIZ: a página individual de cada matriz (uma por paróquia,
   acessível pelo link "Clique aqui" nas páginas de vicariato), que traz o
   horário da matriz E de todas as suas capelas. É uma lista fixa porque
   esses links são montados por JavaScript e não dá pra descobri-los de
   novo em toda execução sem um navegador — se o site criar, renomear ou
   remover uma paróquia, essa lista precisa ser atualizada manualmente.

Como funciona (para cada página, das duas listas):
1. Baixa a URL.
2. Extrai só o miolo da página (ignora o menu/rodapé, que é igual em
   todo o site e não interessa).
3. Compara com o snapshot salvo em monitor/snapshots/.
4. Se for diferente (ou se for a primeira vez), manda e-mail com o
   "antes/depois" e atualiza o snapshot.
5. Se não houver mudança em nenhuma página, não faz nada e não manda e-mail.
"""
import os
import re
import time
import smtplib
import sys
import difflib
from email.mime.text import MIMEText
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PAGINAS = [
    ("urbano_1_e_2_pagina_a", "https://www.arquidiocesedenatal.org.br/cópia-horários-de-missa-2"),
    ("urbano_1_e_2_pagina_b", "https://www.arquidiocesedenatal.org.br/cópia-horários-de-missa"),
    ("norte_1_e_2",           "https://www.arquidiocesedenatal.org.br/horários-de-missa-2"),
    ("sul_1_2_e_3",           "https://www.arquidiocesedenatal.org.br/horários-de-missa-3"),
]

# Uma página por matriz (link "Clique aqui" nas páginas de cada vicariato).
# Traz o horário da matriz E das capelas. Lista fixa — ver docstring acima.
PAGINAS_MATRIZ = [
    ("area_pastoral_de_nossa_senhora_das_dores_ceara_mirim", "https://www.arquidiocesedenatal.org.br/post/%C3%A1rea-pastoral-de-nossa-senhora-das-dores-cear%C3%A1-mirim"),
    ("area_pastoral_de_nossa_senhora_do_rosario_de_fatima_ceara_mirim", "https://www.arquidiocesedenatal.org.br/post/%C3%A1rea-pastoral-de-nossa-senhora-do-ros%C3%A1rio-de-f%C3%A1tima-cear%C3%A1-mirim"),
    ("area_pastoral_de_nossa_senhora_dos_navegantes_rio_do_fogo", "https://www.arquidiocesedenatal.org.br/post/%C3%A1rea-pastoral-de-nossa-senhora-dos-navegantes-rio-do-fogo"),
    ("area_pastoral_de_sao_sebastiao_sitio_novo_rn", "https://www.arquidiocesedenatal.org.br/post/%C3%A1rea-pastoral-de-s%C3%A3o-sebasti%C3%A3o-s%C3%ADtio-novo-rn"),
    ("area_pastoral_do_sagrado_coracao_de_jesus", "https://www.arquidiocesedenatal.org.br/post/%C3%A1rea-pastoral-do-sagrado-cora%C3%A7%C3%A3o-de-jesus"),
    ("area_pastoral_do_sagrado_coracao_de_jesus_poco_branco", "https://www.arquidiocesedenatal.org.br/post/%C3%A1rea-pastoral-do-sagrado-cora%C3%A7%C3%A3o-de-jesus-po%C3%A7o-branco"),
    ("area_pastoral_nossa_senhora_aparecida_sao_jose_de_mipibu", "https://www.arquidiocesedenatal.org.br/post/%C3%A1rea-pastoral-nossa-senhora-aparecida-s%C3%A3o-jos%C3%A9-de-mipibu"),
    ("area_pastoral_quase_paroquia_da_virgem_e_martir_santa_luzia_touros", "https://www.arquidiocesedenatal.org.br/post/%C3%A1rea-pastoral-quase-par%C3%B3quia-da-virgem-e-m%C3%A1rtir-santa-luzia-touros"),
    ("paroquia_da_catedral_de_nossa_senhora_da_apresentacao_natal_1", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-da-catedral-de-nossa-senhora-da-apresenta%C3%A7%C3%A3o-natal-1"),
    ("paroquia_da_imaculada_conceicao_lagoa_salgada", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-da-imaculada-concei%C3%A7%C3%A3o-lagoa-salgada"),
    ("paroquia_da_imaculada_conceicao_nova_alianca_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-da-imaculada-concei%C3%A7%C3%A3o-nova-alian%C3%A7a-natal"),
    ("paroquia_da_imaculada_conceicao_nova_cruz", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-da-imaculada-concei%C3%A7%C3%A3o-nova-cruz"),
    ("paroquia_da_sagrada_familia_rocas_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-da-sagrada-fam%C3%ADlia-rocas-natal"),
    ("paroquia_de_cristo_rei_pirangi_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-cristo-rei-pirangi-natal"),
    ("paroquia_de_nossa_senhora_aparecida_neopolis_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-aparecida-ne%C3%B3polis-natal"),
    ("paroquia_de_nossa_senhora_auxiliadora_felipe_camarao_natal_rn", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-auxiliadora-felipe-camar%C3%A3o-natal-rn"),
    ("paroquia_de_nossa_senhora_da_apresentacao_cidade_alta_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-apresenta%C3%A7%C3%A3o-cidade-alta-natal"),
    ("paroquia_de_nossa_senhora_da_assuncao_guarapes", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-assun%C3%A7%C3%A3o-guarapes"),
    ("paroquia_de_nossa_senhora_da_candelaria_candelaria_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-candel%C3%A1ria-candel%C3%A1ria-natal"),
    ("paroquia_de_nossa_senhora_da_conceicao_canguaretama", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-concei%C3%A7%C3%A3o-canguaretama"),
    ("paroquia_de_nossa_senhora_da_conceicao_ceara_mirim", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-concei%C3%A7%C3%A3o-cear%C3%A1-mirim"),
    ("paroquia_de_nossa_senhora_da_conceicao_guamare", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-concei%C3%A7%C3%A3o-guamar%C3%A9"),
    ("paroquia_de_nossa_senhora_da_conceicao_lajes", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-concei%C3%A7%C3%A3o-lajes"),
    ("paroquia_de_nossa_senhora_da_conceicao_mae_luiza_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-concei%C3%A7%C3%A3o-m%C3%A3e-luiza-natal"),
    ("paroquia_de_nossa_senhora_da_conceicao_macaiba", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-concei%C3%A7%C3%A3o-maca%C3%ADba"),
    ("paroquia_de_nossa_senhora_da_conceicao_macau", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-concei%C3%A7%C3%A3o-macau"),
    ("paroquia_de_nossa_senhora_da_conceicao_maxaranguape", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-concei%C3%A7%C3%A3o-maxaranguape"),
    ("paroquia_de_nossa_senhora_da_conceicao_nova_parnamirim", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-concei%C3%A7%C3%A3o-nova-parnamirim"),
    ("paroquia_de_nossa_senhora_da_conceicao_sao_rafael", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-concei%C3%A7%C3%A3o-s%C3%A3o-rafael"),
    ("paroquia_de_nossa_senhora_da_conceicao_sao_tome", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-concei%C3%A7%C3%A3o-s%C3%A3o-tom%C3%A9"),
    ("paroquia_de_nossa_senhora_da_conceicao_santa_maria", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-concei%C3%A7%C3%A3o-santa-maria"),
    ("paroquia_de_nossa_senhora_da_conceicao_santo_antonio", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-concei%C3%A7%C3%A3o-santo-ant%C3%B4nio"),
    ("paroquia_de_nossa_senhora_da_conceicao_serra_caiada", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-concei%C3%A7%C3%A3o-serra-caiada"),
    ("paroquia_de_nossa_senhora_da_penha_monte_alegre", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-penha-monte-alegre"),
    ("paroquia_de_nossa_senhora_da_piedade_espirito_santo", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-piedade-esp%C3%ADrito-santo"),
    ("paroquia_de_nossa_senhora_da_pureza_pureza", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-pureza-pureza"),
    ("paroquia_de_nossa_senhora_da_saude_boa_saude", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-da-sa%C3%BAde-boa-sa%C3%BAde"),
    ("paroquia_de_nossa_senhora_das_dores_brejinho", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-das-dores-brejinho"),
    ("paroquia_de_nossa_senhora_das_gracas_afonso_bezerra", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-das-gra%C3%A7as-afonso-bezerra"),
    ("paroquia_de_nossa_senhora_das_gracas_e_santa_teresinha_tirol_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-das-gra%C3%A7as-e-santa-teresinha-tirol-natal"),
    ("paroquia_de_nossa_senhora_de_fatima_macaiba", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-de-f%C3%A1tima-maca%C3%ADba"),
    ("paroquia_de_nossa_senhora_de_fatima_parnamirim", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-de-f%C3%A1tima-parnamirim"),
    ("paroquia_de_nossa_senhora_de_fatima_passa_e_fica", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-de-f%C3%A1tima-passa-e-fica"),
    ("paroquia_de_nossa_senhora_de_lourdes_areia_preta_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-de-lourdes-areia-preta-natal"),
    ("paroquia_de_nossa_senhora_de_lourdes_campo_redondo", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-de-lourdes-campo-redondo"),
    ("paroquia_de_nossa_senhora_de_lourdes_ipanguacu", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-de-lourdes-ipangua%C3%A7u"),
    ("paroquia_de_nossa_senhora_de_nazare_parazinho", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-de-nazar%C3%A9-parazinho"),
    ("paroquia_de_nossa_senhora_do_o_nisia_floresta", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-do-%C3%B3-n%C3%ADsia-floresta"),
    ("paroquia_de_nossa_senhora_do_amparo_coronel_ezequiel", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-do-amparo-coronel-ezequiel"),
    ("paroquia_de_nossa_senhora_do_carmo_parque_das_nacoes_parnamirim", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-do-carmo-parque-das-na%C3%A7%C3%B5es-parnamirim"),
    ("paroquia_de_nossa_senhora_do_livramento_taipu_rn", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-do-livramento-taipu-rn"),
    ("paroquia_de_nossa_senhora_do_perpetuo_socorro_barcelona", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-do-perp%C3%A9tuo-socorro-barcelona"),
    ("paroquia_de_nossa_senhora_do_perpetuo_socorro_quintas_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-do-perp%C3%A9tuo-socorro-quintas-natal"),
    ("paroquia_de_nossa_senhora_do_rosario_alto_do_rodrigues", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-do-ros%C3%A1rio-alto-do-rodrigues"),
    ("paroquia_de_nossa_senhora_dos_navegantes_redinha_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-dos-navegantes-redinha-natal"),
    ("paroquia_de_nossa_senhora_dos_prazeres_goianinha", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-dos-prazeres-goianinha"),
    ("paroquia_de_nossa_senhora_mae_dos_homens_joao_camara", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-m%C3%A3e-dos-homens-jo%C3%A3o-c%C3%A2mara"),
    ("paroquia_de_nossa_senhora_rainha_da_paz_nova_parnamirim", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-rainha-da-paz-nova-parnamirim"),
    ("paroquia_de_nossa_senhora_virgem_dos_pobres_emaus", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-senhora-virgem-dos-pobres-ema%C3%BAs"),
    ("paroquia_de_nossa_sra_dos_impossiveis_pitimbu_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-nossa-sra-dos-imposs%C3%ADveis-pitimbu-natal"),
    ("paroquia_de_sao_bento_abade_serra_de_sao_bento", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-bento-abade-serra-de-s%C3%A3o-bento"),
    ("paroquia_de_sao_camilo_de_lellis_lagoa_nova_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-camilo-de-l%C3%A9llis-lagoa-nova-natal"),
    ("paroquia_de_sao_francisco_de_assis_cidade_satelite_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-francisco-de-assis-cidade-sat%C3%A9lite-natal"),
    ("paroquia_de_sao_francisco_de_assis_e_sao_joao_lostau_navarro_pirangi_d", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-francisco-de-assis-e-s%C3%A3o-jo%C3%A3o-lostau-navarro-pirangi-do-norte"),
    ("paroquia_de_sao_francisco_de_assis_lagoa_de_pedras", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-francisco-de-assis-lagoa-de-pedras"),
    ("paroquia_de_sao_francisco_de_assis_pedro_velho", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-francisco-de-assis-pedro-velho"),
    ("paroquia_de_sao_goncalo_do_amarante", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-gon%C3%A7alo-do-amarante"),
    ("paroquia_de_sao_joao_batista_arez", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-jo%C3%A3o-batista-arez"),
    ("paroquia_de_sao_joao_batista_lagoa_seca_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-jo%C3%A3o-batista-lagoa-seca-natal"),
    ("paroquia_de_sao_joao_batista_montanhas", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-jo%C3%A3o-batista-montanhas"),
    ("paroquia_de_sao_joao_batista_pendencias", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-jo%C3%A3o-batista-pend%C3%AAncias"),
    ("paroquia_de_sao_joao_batista_praia_de_pitangui", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-jo%C3%A3o-batista-praia-de-pitangui"),
    ("paroquia_de_sao_joao_batista_vila_de_ponta_negra_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-jo%C3%A3o-batista-vila-de-ponta-negra-natal"),
    ("paroquia_de_sao_joao_bosco_gramore_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-jo%C3%A3o-bosco-gramor%C3%A9-natal"),
    ("paroquia_de_sao_jose_angicos", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-jos%C3%A9-angicos"),
    ("paroquia_de_sao_jose_cidade_nova_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-jos%C3%A9-cidade-nova-natal"),
    ("paroquia_de_sao_jose_de_anchieta_lagoa_nova_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-jos%C3%A9-de-anchieta-lagoa-nova-natal"),
    ("paroquia_de_sao_jose_operario_jandaira", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-jos%C3%A9-oper%C3%A1rio-janda%C3%ADra"),
    ("paroquia_de_sao_jose_sao_jose_de_campestre", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-jos%C3%A9-s%C3%A3o-jos%C3%A9-de-campestre"),
    ("paroquia_de_sao_lucas_conjunto_amarante_sao_goncalo_do_amarante", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-lucas-conjunto-amarante-s%C3%A3o-gon%C3%A7alo-do-amarante"),
    ("paroquia_de_sao_mateus_moreira_cidade_verde", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-mateus-moreira-cidade-verde"),
    ("paroquia_de_sao_miguel_arcanjo_sao_miguel_do_gostoso", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-miguel-arcanjo-s%C3%A3o-miguel-do-gostoso"),
    ("paroquia_de_sao_miguel_extremoz", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-miguel-extremoz"),
    ("paroquia_de_sao_paulo_apostolo_pedro_avelino", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-paulo-ap%C3%B3stolo-pedro-avelino"),
    ("paroquia_de_sao_paulo_apostolo_sao_paulo_do_potengi", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-paulo-ap%C3%B3stolo-s%C3%A3o-paulo-do-potengi"),
    ("paroquia_de_sao_pedro_apostolo_alecrim_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-pedro-ap%C3%B3stolo-alecrim-natal"),
    ("paroquia_de_sao_pedro_apostolo_sao_pedro", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-pedro-ap%C3%B3stolo-s%C3%A3o-pedro"),
    ("paroquia_de_sao_pedro_apostolo_varzea", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-pedro-ap%C3%B3stolo-v%C3%A1rzea"),
    ("paroquia_de_sao_pedro_pescador_baia_formosa", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-pedro-pescador-ba%C3%ADa-formosa"),
    ("paroquia_de_sao_sebastiao_alecrim_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-sebasti%C3%A3o-alecrim-natal"),
    ("paroquia_de_sao_sebastiao_japi", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-sebasti%C3%A3o-japi"),
    ("paroquia_de_sao_tiago_menor_santarem_natal_rn", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-tiago-menor-santar%C3%A9m-natal-rn"),
    ("paroquia_de_sao_tome_apostolo_conj_cidade_do_sol_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-tom%C3%A9-ap%C3%B3stolo-conj-cidade-do-sol-natal"),
    ("paroquia_de_sao_vicente_ferrer_itaja", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-s%C3%A3o-vicente-f%C3%A9rrer-itaj%C3%A1"),
    ("paroquia_de_sant_ana_capim_macio_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-sant-ana-capim-macio-natal"),
    ("paroquia_de_sant_ana_e_sao_joaquim_sao_jose_de_mipibu", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-sant-ana-e-s%C3%A3o-joaquim-s%C3%A3o-jos%C3%A9-de-mipibu"),
    ("paroquia_de_sant_ana_sant_ana_do_matos", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-sant-ana-sant-ana-do-matos"),
    ("paroquia_de_sant_ana_soledade_2_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-sant-ana-soledade-2-natal"),
    ("paroquia_de_santa_clara_pitimbu_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-santa-clara-pitimbu-natal"),
    ("paroquia_de_santa_luzia_boa_esperanca_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-santa-luzia-boa-esperan%C3%A7a-natal"),
    ("paroquia_de_santa_maria_mae_conj_santa_catarina_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-santa-maria-m%C3%A3e-conj-santa-catarina-natal"),
    ("paroquia_de_santa_rita_de_cassia_dos_impossiveis_ponta_negra_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-santa-rita-de-c%C3%A1ssia-dos-imposs%C3%ADveis-ponta-negra-natal"),
    ("paroquia_de_santa_rita_de_cassia_santa_cruz", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-santa-rita-de-c%C3%A1ssia-santa-cruz"),
    ("paroquia_de_santa_teresinha_lagoa_d_anta", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-santa-teresinha-lagoa-d-anta"),
    ("paroquia_de_santa_teresinha_tangara", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-santa-teresinha-tangar%C3%A1"),
    ("paroquia_de_santo_afonso_maria_de_ligorio_mirassol_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-santo-afonso-maria-de-lig%C3%B3rio-mirassol-natal"),
    ("paroquia_de_santo_antao_abade_sao_bento_do_norte", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-santo-ant%C3%A3o-abade-s%C3%A3o-bento-do-norte"),
    ("paroquia_de_santo_antonio_de_lisboa_tibau_do_sul", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-santo-ant%C3%B4nio-de-lisboa-tibau-do-sul"),
    ("paroquia_de_santo_antonio_de_padua_parque_dos_coqueiros_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-santo-ant%C3%B4nio-de-p%C3%A1dua-parque-dos-coqueiros-natal"),
    ("paroquia_de_santo_antonio_santo_antonio_do_potengi", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-santo-ant%C3%B4nio-santo-ant%C3%B4nio-do-potengi"),
    ("paroquia_de_santo_antonio_serrinha", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-santo-ant%C3%B4nio-serrinha"),
    ("paroquia_de_santo_expedito_jardim_petropolis", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-santo-expedito-jardim-petr%C3%B3polis"),
    ("paroquia_de_santos_reis_parnamirim", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-de-santos-reis-parnamirim"),
    ("paroquia_do_bom_jesus_das_dores_ribeira_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-do-bom-jesus-das-dores-ribeira-natal"),
    ("paroquia_do_bom_jesus_dos_navegantes_touros", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-do-bom-jesus-dos-navegantes-touros"),
    ("paroquia_do_divino_espirito_santo_vera_cruz", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-do-divino-esp%C3%ADrito-santo-vera-cruz"),
    ("paroquia_do_sagrado_coracao_de_jesus_bom_jesus", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-do-sagrado-cora%C3%A7%C3%A3o-de-jesus-bom-jesus"),
    ("paroquia_do_sagrado_coracao_de_jesus_morro_branco_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-do-sagrado-cora%C3%A7%C3%A3o-de-jesus-morro-branco-natal"),
    ("paroquia_do_sagrado_coracao_de_jesus_riachuelo", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-do-sagrado-cora%C3%A7%C3%A3o-de-jesus-riachuelo"),
    ("paroquia_do_santo_ambrosio_francisco_ferro_planalto", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-do-santo-ambr%C3%B3sio-francisco-ferro-planalto"),
    ("paroquia_do_santo_andre_de_soveral_jardim_aeroporto", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-do-santo-andr%C3%A9-de-soveral-jardim-aeroporto"),
    ("paroquia_do_santuario_dos_santos_martires_de_cunhau_e_uruacu_nazare_na", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-do-santu%C3%A1rio-dos-santos-m%C3%A1rtires-de-cunha%C3%BA-e-urua%C3%A7u-nazar%C3%A9-natal"),
    ("paroquia_jesus_bom_pastor_bom_pastor_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-jesus-bom-pastor-bom-pastor-natal"),
    ("paroquia_sao_miguel_arcanjo_parnamirim", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-s%C3%A3o-miguel-arcanjo-parnamirim"),
    ("paroquia_santuario_de_nossa_senhora_da_esperanca_e_santo_inacio_de_loy", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-santu%C3%A1rio-de-nossa-senhora-da-esperan%C3%A7a-e-santo-in%C3%A1cio-de-loyola"),
    ("paroquia_santuario_de_nossa_senhora_de_fatima_parque_das_dunas_natal", "https://www.arquidiocesedenatal.org.br/post/par%C3%B3quia-santu%C3%A1rio-de-nossa-senhora-de-f%C3%A1tima-parque-das-dunas-natal"),
]

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
SNAPSHOTS_MATRIZ_DIR = SNAPSHOTS_DIR / "matrizes"
SNAPSHOTS_MATRIZ_DIR.mkdir(parents=True, exist_ok=True)

MARCA_INICIO = "Use tab to navigate through the menu items."
MARCA_FIM = "bottom of page"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (monitor-horarios-missa)"})


def baixar_html(url: str) -> str:
    resp = SESSION.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def texto_da_pagina(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    texto = soup.get_text("\n")
    return re.sub(r"\n{2,}", "\n", texto).strip()


def baixar_conteudo(url: str) -> str:
    """Extrai o miolo de uma página-resumo (PAGINAS)."""
    texto = texto_da_pagina(baixar_html(url))

    ini = texto.find(MARCA_INICIO)
    fim = texto.find(MARCA_FIM)
    if ini != -1:
        texto = texto[ini + len(MARCA_INICIO):]
    if fim != -1:
        fim2 = texto.find(MARCA_FIM)
        if fim2 != -1:
            texto = texto[:fim2]
    return texto.strip()


def baixar_conteudo_matriz(url: str) -> str:
    """Extrai o bloco 'Horário(s) de missas' da página individual de uma matriz."""
    texto = texto_da_pagina(baixar_html(url))

    # a página tem os mesmos itens de menu duas vezes (menu + rodapé/breadcrumb);
    # "Buscar" só aparece depois do menu, logo antes do conteúdo real do post.
    inicio_conteudo = texto.rfind("Buscar")
    if inicio_conteudo == -1:
        inicio_conteudo = 0

    m = re.search(r"Hor[aá]rios?\s+d?e?a?s?\s*missas?", texto[inicio_conteudo:], re.I)
    if not m:
        return ""
    ini = inicio_conteudo + m.start()

    fim = len(texto)
    for marca in ("Funcionamento da secretaria", "Bairros que abrange",
                  "Data de criação", "Data de cria", "Posts recentes", "visualizações"):
        pos = texto.find(marca, ini)
        if pos != -1:
            fim = min(fim, pos)

    return texto[ini:fim].strip()


def enviar_email(assunto: str, corpo: str):
    remetente = os.environ["SMTP_USER"]
    senha = os.environ["SMTP_PASS"]
    destinatario = os.environ["ALERT_EMAIL_TO"]

    msg = MIMEText(corpo, "plain", "utf-8")
    msg["Subject"] = assunto
    msg["From"] = remetente
    msg["To"] = destinatario

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as servidor:
        servidor.login(remetente, senha)
        servidor.sendmail(remetente, [destinatario], msg.as_string())


def checar_paginas(paginas, snapshots_dir, extrair, relatorios, pausa=0.0):
    houve_mudanca = False
    for slug, url in paginas:
        snapshot_path = snapshots_dir / f"{slug}.txt"
        try:
            atual = extrair(url)
        except Exception as e:
            aviso = f"⚠️ Não consegui acessar {url}\nErro: {e}\n"
            print(f"[{slug}] {aviso}")
            relatorios.append(aviso)
            continue
        finally:
            if pausa:
                time.sleep(pausa)

        if not atual:
            aviso = f"⚠️ Não encontrei o bloco de horários em {url} (pode ter mudado de formato, ou a página ainda não tem horário publicado)\n"
            print(f"[{slug}] {aviso}")
            relatorios.append(aviso)
            continue

        if not snapshot_path.exists():
            snapshot_path.write_text(atual, encoding="utf-8")
            print(f"[{slug}] primeira checagem — snapshot salvo, sem alerta.")
            continue

        anterior = snapshot_path.read_text(encoding="utf-8")
        if anterior.strip() == atual.strip():
            print(f"[{slug}] sem mudanças.")
            continue

        houve_mudanca = True
        diff = "\n".join(difflib.unified_diff(
            anterior.splitlines(), atual.splitlines(),
            lineterm="", fromfile="antes", tofile="depois"
        ))
        relatorios.append(f"### Mudança detectada em: {url}\n\n{diff}\n")
        snapshot_path.write_text(atual, encoding="utf-8")
    return houve_mudanca


def main():
    # garante utf-8 na saída (evita crash em consoles com outra codificação)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    relatorios = []

    houve_mudanca_resumo = checar_paginas(PAGINAS, SNAPSHOTS_DIR, baixar_conteudo, relatorios)
    houve_mudanca_matriz = checar_paginas(PAGINAS_MATRIZ, SNAPSHOTS_MATRIZ_DIR, baixar_conteudo_matriz, relatorios, pausa=0.3)
    houve_mudanca = houve_mudanca_resumo or houve_mudanca_matriz

    if houve_mudanca:
        corpo = (
            "O site da Arquidiocese de Natal mudou uma ou mais páginas de "
            "horários de missa (resumo do vicariato ou página individual de "
            "alguma matriz/capela).\n\n" + "\n\n".join(relatorios) +
            "\n\nConfira o site oficial e, se necessário, atualize a "
            "planilha do app Horário de Missas."
        )
        enviar_email("⛪ Mudança nos horários de missa - Arquidiocese de Natal", corpo)
        print("E-mail de alerta enviado.")
    else:
        print("Nenhuma mudança encontrada. Nenhum e-mail enviado.")

    # sinaliza pro workflow se precisa commitar novos snapshots
    Path("monitor/.mudou").write_text("1" if houve_mudanca else "0")


if __name__ == "__main__":
    sys.exit(main())
