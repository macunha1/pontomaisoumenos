Ponto MaisOuMenos
---

> Agendador de ponto no pontomais.com.br inserindo uma localidade escolhida.

### Motivação

A preguiça de ficar batendo ponto, que é uma tarefa repetitiva e mecânica deu origem a essa aplicação. Ela foi construída tendo como base o [pontomenos](https://github.com/gustavohenrique/pontomenos)

Mas, o Ponto MaisOuMenos tem um agendador para bater ponto, e também métodos para fazer jornadas de trabalho variadas, definindo horas em que (mais ou menos) você costuma chegar e sair.

### Configurações

Para conseguir utilizar o pontomaisoumenos, você precisará configurar no arquivo de [configurações](config/default.toml) os horários, local de trabalho e usuário do pontomais:

```toml
[working_hours]
possible_minutes_variation_start = 0 # Minuto em que deseja começar os valores
possible_minutes_variation_end = 59 # Minuto em que deseja terminar
possible_start_hour = 9 # Hora para começar os valores randomicos
lunch_time = 1 # Tempo de almoço para considerar na conta
accepted_start_hour_variation = 1.23 # Variação na hora inicial
maximum_daily_working_hours = 10 # Quantidade máxima de horas para "trabalhar" por dia
expected_daily_hours = 8 # Quantidade de horas que se espera "trabalhar" por dia

# Localização precisará do endereço e da geolocation
# A Geolocation pode ser conseguida no Google Maps, clickando com o botão direito e indo em "O que há aqui?"
[location]
address = "Av. Paulista, 2300 - Bela Vista, São Paulo - SP, Brasil"
latitude = -23.556828
longitude = -46.6618655

# Usuário e senha do pontomais
[user]
email = some@email.com
password = topsecret!too

# Configuração do banco, o default está para o container no docker-compose.yml
[database]
type = postgresql
driver = psycopg2
database = working_hours
endpoint = postgres-01
port = 5432
username = dev
password = topsecret!
connection_string = %(type)s+%(driver)s://%(username)s:%(password)s@%(endpoint)s:%(port)s/

# Configuração do message broker para ser utilizado pelo dramatiq, default também é o do docker-compose.yml
[message_broker]
type = redis
database = 0
endpoint = redis-01
port = 6379
connection_string = %(type)s://%(endpoint)s:%(port)s/%(database)s

[logging]
level = DEBUG
```

### Executando

Na primeira execução será necessário configurar o banco, portanto, rodar a(s) migration(s)

```sh
make RUN_MIGRATIONS=yes dev
```

Isso já irá iniciar o Docker compose e criar todos os containers, basta deixar em algum lugar (server, Ec2, raspberry, whatever) para executar as tarefas.

A aplicação irá pegar o calendário de dias úteis no mês (de acordo com a Wikipedia), multiplicar pela quantidade de horas que se deve trabalhar por dia, e então rodar um algoritmo genético para criar as possíveis gerações e escolher uma.

### Erros conhecidos

- Caso a aplicação esteja com o logger configurado corretamente, e não apresente os registros é porque o algoritmo entrou em loop infinito tentando inferir as datas para bater o ponto, portanto, é necessário ajustar o arquivo de configuração para que ele consiga criar uma quantidade de horas válida no mês.

### Atenção ⚠

A utilização desse agendador é de total responsabilidade do usuário, saiba dos riscos com relação às leis trabalhistas antes de qualquer coisa.

Use com moderação :D
