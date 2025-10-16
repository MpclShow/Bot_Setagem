
import discord
from flask import Flask
from threading import Thread
from discord.ext import commands
from discord import app_commands
import os
import sqlite3
from discord.ui import View, button, Modal, TextInput, Select
from datetime import datetime, timedelta
import asyncio
from datetime import datetime
import pytz  # pip install pytz

config_global = {}


# --- Mantenha o bot online ---

app = Flask('')


@app.route('/')
def main():
    return "O bot  está online! ver. 0.0.2"


def run():
    app.run(host="0.0.0.0", port=8080)


def keep_alive():
    server = Thread(target=run)
    server.start()
# -----------------------------


TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
DB_FILE = "config.db"

# -------------------- Funções utilitárias --------------------


def normalizar_sim_nao(valor: str) -> str:
    valor = valor.strip().lower()
    if valor in ["sim", "s", "yes", "y"]:
        return "sim"
    elif valor in ["não", "nao", "n", "no"]:
        return "não"
    return None

def criar_nivel(guild_id: int, nivel: int, nome: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO niveis (guild_id, nivel, nome) VALUES (?, ?, ?)",
        (str(guild_id), nivel, nome)
    )
    conn.commit()
    conn.close()


def definir_acao_nivel(guild_id: int, nivel: int, acao: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO acoes_por_nivel (guild_id, nivel, acao) VALUES (?, ?, ?)",
        (str(guild_id), nivel, acao)
    )
    conn.commit()
    conn.close()


def obter_acoes_nivel(guild_id: int, nivel: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT acao FROM acoes_por_nivel WHERE guild_id=? AND nivel=?",
        (str(guild_id), nivel)
    )
    resultados = [row[0] for row in c.fetchall()]
    conn.close()
    return resultados


def niveis_disponiveis(guild_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT nivel FROM niveis WHERE guild_id=? ORDER BY nivel ASC",
        (str(guild_id),)
    )
    resultados = [row[0] for row in c.fetchall()]
    conn.close()
    return resultados

    # Função utilitária para remover do banco (já existente ou adaptada)
def remover_cadastro(guild_id: int, usuario_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "DELETE FROM recrutamentos WHERE guild_id=? AND usuario_id=?",
        (str(guild_id), str(usuario_id))
    )
    conn.commit()
    conn.close()


# Evento que dispara quando alguém sai do servidor
@bot.event
async def on_member_remove(member: discord.Member):
    try:
        # Remove do banco de dados
        remover_cadastro(member.guild.id, member.id)

        # Busca canal de log, se configurado
        config = carregar_config(member.guild.id)
        if config and config.get("canal_log_id"):
            canal_log = member.guild.get_channel(config["canal_log_id"])
            if canal_log:
                embed = discord.Embed(
                    title="🚪 Membro saiu do servidor",
                    description=f"O membro {member.mention} foi removido do cadastro automaticamente.",
                    color=discord.Color.orange()
                )
                await canal_log.send(embed=embed)
        print(f"✅ Cadastro de {member} removido automaticamente ao sair do servidor.")
    except Exception as e:
        print(f"❌ Erro ao processar saída de membro: {e}")



# -------------------- Banco de dados --------------------


def criar_tabelas():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # ---------------- Tabela de Configuração ----------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS config (
            guild_id TEXT PRIMARY KEY,
            cargo_padrao TEXT NOT NULL,
            cargo_crianca TEXT,
            canal_solicitacao_id INTEGER NOT NULL,
            canal_log_id INTEGER,
            canal_confirmacao_id INTEGER,
            prefixo TEXT DEFAULT 'APR',
            prefixo_criancas TEXT DEFAULT 'APR',
            trabalha_com_criancas TEXT DEFAULT 'não',
            mensagem_id INTEGER,
            mensagem_botao TEXT DEFAULT 'Clique abaixo para solicitar seu recrutamento:'
        )
    """)
    
    # ---------------- Tabela de Cargos por Permissão ----------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS cargos_permissao (
            guild_id TEXT,
            nivel INTEGER,
            cargo_nome TEXT,
            PRIMARY KEY (guild_id, nivel, cargo_nome)
        )
    """)
    
    # ---------------- Tabela de Recrutamentos ----------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS recrutamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT NOT NULL,
            recrutador_id TEXT NOT NULL,
            usuario_id TEXT NOT NULL,
            data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # ---------------- Tabela de Níveis Dinâmicos ----------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS niveis (
            guild_id TEXT,
            nivel INTEGER,
            nome TEXT,
            PRIMARY KEY (guild_id, nivel)
        )
    """)
    
    # ---------------- Tabela de Ações por Nível ----------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS acoes_por_nivel (
            guild_id TEXT,
            nivel INTEGER,
            acao TEXT,
            PRIMARY KEY (guild_id, nivel, acao)
        )
    """)
    
    conn.commit()
    conn.close()

criar_tabelas()



def salvar_config(guild_id, cargo_padrao, canal_solicitacao_id, canal_log_id=None, prefixo="APR", prefixo_criancas="APR", trabalha_com_criancas="não", cargo_crianca=None, mensagem_id=None, mensagem_botao=None, canal_confirmacao_id=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO config (guild_id, cargo_padrao, cargo_crianca, canal_solicitacao_id, canal_log_id, canal_confirmacao_id, prefixo, prefixo_criancas, trabalha_com_criancas, mensagem_id, mensagem_botao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            cargo_padrao=excluded.cargo_padrao,
            cargo_crianca=excluded.cargo_crianca,
            canal_solicitacao_id=excluded.canal_solicitacao_id,
            canal_log_id=excluded.canal_log_id,
            canal_confirmacao_id=COALESCE(excluded.canal_confirmacao_id, config.canal_confirmacao_id),
            prefixo=excluded.prefixo,
            prefixo_criancas=excluded.prefixo_criancas,
            trabalha_com_criancas=excluded.trabalha_com_criancas,
            mensagem_id=COALESCE(excluded.mensagem_id, config.mensagem_id),
            mensagem_botao=COALESCE(excluded.mensagem_botao, config.mensagem_botao)
    """, (str(guild_id), cargo_padrao, cargo_crianca, canal_solicitacao_id, canal_log_id, canal_confirmacao_id, prefixo, prefixo_criancas, trabalha_com_criancas, mensagem_id, mensagem_botao))
    conn.commit()
    conn.close()


def carregar_config(guild_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT cargo_padrao, cargo_crianca, canal_solicitacao_id, canal_log_id, canal_confirmacao_id, prefixo, prefixo_criancas, trabalha_com_criancas, mensagem_id, mensagem_botao
        FROM config WHERE guild_id = ?
    """, (str(guild_id),))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "cargo_padrao": row[0],
            "cargo_crianca": row[1],
            "canal_solicitacao_id": row[2],
            "canal_log_id": row[3],
            "canal_confirmacao_id": row[4],
            "prefixo": row[5],
            "prefixo_criancas": row[6],
            "trabalha_com_criancas": row[7].lower(),
            "mensagem_id": row[8],
            "mensagem_botao": row[9] or "Clique abaixo para solicitar seu recrutamento:"
        }
    return None


def adicionar_coluna_tempo_expiracao():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute(
            "ALTER TABLE config ADD COLUMN tempo_expiracao INTEGER DEFAULT 10")
    except sqlite3.OperationalError:
        # A coluna já existe
        pass
    conn.commit()
    conn.close()


adicionar_coluna_tempo_expiracao()


# -------------------- Permissões --------------------


# Adiciona cargo a nível dinâmico
def adicionar_cargo_permissao(guild_id, nivel, cargo_nome):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO cargos_permissao (guild_id, nivel, cargo_nome) VALUES (?, ?, ?)",
        (str(guild_id), nivel, cargo_nome)
    )
    conn.commit()
    conn.close()

# Remove cargo de um nível
def remover_cargo_permissao(guild_id, nivel, cargo_nome):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "DELETE FROM cargos_permissao WHERE guild_id=? AND nivel=? AND cargo_nome=?",
        (str(guild_id), nivel, cargo_nome)
    )
    conn.commit()
    conn.close()

# Checa se um usuário tem permissão de determinado nível
def checar_permissao_multiplos_niveis(user, niveis):
    """
    Verifica se o usuário possui permissão em um ou mais níveis definidos.
    Pode receber um único nível (int/str) ou uma lista de níveis ([0, 1, 2...]).
    """
    try:
        with sqlite3.connect('config.db') as conn:
            c = conn.cursor()

            # Garante que 'niveis' é sempre uma lista
            if not isinstance(niveis, list):
                niveis = [niveis]

            # Cria placeholders (?) conforme a quantidade de níveis
            placeholders = ','.join(['?'] * len(niveis))
            params = [str(user.guild.id)] + [str(n) for n in niveis]

            # Busca cargos que correspondem aos níveis informados
            c.execute(
                f"""
                SELECT cargo_nome FROM cargos_permissao
                WHERE guild_id=? AND nivel IN ({placeholders})
                """,
                params
            )
            cargos = [row[0] for row in c.fetchall()]

            # Verifica se o usuário possui algum desses cargos
            for cargo_nome in cargos:
                cargo = discord.utils.get(user.guild.roles, name=cargo_nome)
                if cargo in user.roles:
                    return True  # Usuário tem permissão

        # Se nenhum cargo foi encontrado ou o usuário não os possui
        return False

    except Exception as e:
        print(f"Erro em checar_permissao_multiplos_niveis: {e}")
        return False

        
# Retorna lista de membros com permissão em qualquer dos níveis fornecidos
def niveis_disponiveis_guild(guild_id: int):
    """Retorna todos os níveis configurados no servidor."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT DISTINCT nivel FROM cargos_permissao WHERE guild_id=? ORDER BY nivel ASC",
        (str(guild_id),)
    )
    niveis = [row[0] for row in c.fetchall()]
    conn.close()
    return niveis

def membros_com_permissao_dinamico(guild: discord.Guild):
    """Retorna todos os membros que possuem permissão em algum nível configurado."""
    niveis = niveis_disponiveis_guild(guild.id)
    membros_autorizados = []

    for membro in guild.members:
        if checar_permissao_multiplos_niveis(membro, niveis):
            membros_autorizados.append(membro)

    return membros_autorizados


# -------------------- Registro de recrutamento --------------------


def registrar_recrutamento(guild_id, recrutador_id, usuario_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO recrutamentos (guild_id, recrutador_id, usuario_id)
        VALUES (?, ?, ?)
    """, (str(guild_id), str(recrutador_id), str(usuario_id)))
    conn.commit()
    conn.close()

# -------------------- Bot ready --------------------


def carregar_config_global():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT guild_id, tempo_expiracao FROM config")
    for guild_id, tempo in c.fetchall():
        if guild_id not in config_global:
            config_global[guild_id] = {}
        config_global[guild_id]["tempo_expiracao"] = tempo
    conn.close()


carregar_config_global()


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot online como {bot.user}")
    print("📋 Comandos de barra sincronizados.")
    print("O bot  está online! ver. 0.0.1.2")

# -------------------- Modal de Solicitação --------------------


class RecrutamentoModal(Modal, title="📋 Solicitação de Recrutamento"):
    def __init__(self, config, recrutador_member: discord.Member):
        super().__init__()
        self.config = config
        self.recrutador_member = recrutador_member
        self.nome = TextInput(label="Nome no servidor",
                              placeholder="Ex: Nome no Jogo", required=True)
        self.id_jogo = TextInput(
            label="ID do jogo", placeholder="Ex: 1234", required=True)
        self.tel_jogo = TextInput(
            label="Tel do jogo", placeholder="Ex: 123-456", required=True)
        self.add_item(self.nome)
        self.add_item(self.id_jogo)
        self.add_item(self.tel_jogo)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        config = self.config
        if normalizar_sim_nao(config["trabalha_com_criancas"]) == "sim" and config.get("cargo_crianca"):
            cargo = discord.utils.get(
                guild.roles, name=config["cargo_crianca"])
            prefixo_usado = config.get(
                "prefixo_criancas", config.get("prefixo", "APR"))
        else:
            cargo = discord.utils.get(guild.roles, name=config["cargo_padrao"])
            prefixo_usado = config.get("prefixo", "APR")
        if not cargo:
            await interaction.response.send_message(f"❌ Cargo `{cargo.name if cargo else 'N/A'}` não encontrado.", ephemeral=True)
            return

        if config.get("canal_confirmacao_id"):
            canal_confirmacao = guild.get_channel(
                config["canal_confirmacao_id"])
            if canal_confirmacao:
                embed = discord.Embed(
                    title="📋 Solicitação de Setagem", color=discord.Color.yellow())
                embed.add_field(
                    name="Usuário", value=interaction.user.mention, inline=False)
                embed.add_field(
                    name="Nome", value=self.nome.value, inline=False)
                embed.add_field(
                    name="TEL", value=self.tel_jogo.value, inline=False)
                embed.add_field(
                    name="ID", value=self.id_jogo.value, inline=False)
                embed.add_field(
                    name="Cargo", value=cargo.mention, inline=False)
                embed.add_field(
                    name="Recrutador", value=self.recrutador_member.mention, inline=False)
                view = ConfirmacaoView(
                    interaction.user, f"{prefixo_usado} | {self.nome.value} | {self.id_jogo.value}", self.tel_jogo.value, cargo, self.recrutador_member, config)
                await canal_confirmacao.send(embed=embed, view=view)
                await interaction.response.send_message(f"✅ Sua solicitação foi enviada para aprovação em {canal_confirmacao.mention}", ephemeral=True)

# -------------------- View de Aprovação --------------------


class ConfirmacaoView(View):
    bloqueios = set()  # Guarda IDs de usuários sendo processados (aprovação ou rejeição)

    def __init__(self, usuario: discord.Member, nick: str, tel: str, cargo: discord.Role, recrutador: discord.Member, config):
        tempo_exp = config.get("tempo_expiracao", 10)
        super().__init__(timeout=tempo_exp * 60)
        self.usuario = usuario
        self.nick = nick
        self.tel = tel
        self.cargo = cargo
        self.recrutador = recrutador
        self.config = config

    async def processar(self, interaction: discord.Interaction, acao: str):
        guild = interaction.guild
        membro = self.usuario

        if membro.id in ConfirmacaoView.bloqueios:
            await interaction.response.send_message(
                "⚠️ Já existe uma ação em andamento para este recrutamento.",
                ephemeral=True
            )
            return
        ConfirmacaoView.bloqueios.add(membro.id)

        try:
            if not checar_permissao_multiplos_niveis(interaction.user, [0, 1]):
                await interaction.response.send_message(
                    f"❌ Você não tem permissão para {acao}.",
                    ephemeral=True
                )
                return

            if interaction.user.id == self.usuario.id:
                await interaction.response.send_message(
                    f"⚠️ Você não pode {acao} a si mesmo.",
                    ephemeral=True
                )
                if self.config.get("canal_log_id"):
                    canal_log = guild.get_channel(self.config["canal_log_id"])
                    if canal_log:
                        embed_log = discord.Embed(
                            title="🚫 Tentativa de autoação bloqueada",
                            description=f"{interaction.user.mention} tentou {acao} a própria solicitação.",
                            color=discord.Color.orange()
                        )
                        await canal_log.send(embed=embed_log)
                return

            cargo_padrao = discord.utils.get(
                guild.roles, name=self.config["cargo_padrao"])
            cargo_crianca = discord.utils.get(
                guild.roles, name=self.config.get("cargo_crianca"))
            if cargo_padrao in membro.roles or (cargo_crianca and cargo_crianca in membro.roles):
                await interaction.response.send_message(
                    f"⚠️ O membro {membro.mention} já está setado.",
                    ephemeral=True
                )
                return

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute(
                "SELECT 1 FROM recrutamentos WHERE guild_id=? AND usuario_id=?",
                (str(guild.id), str(membro.id))
            )
            ja_registrado = c.fetchone()
            conn.close()

            if ja_registrado and acao == "aprovar":
                await interaction.response.send_message(
                    f"⚠️ O membro {membro.mention} já possui um registro de recrutamento.",
                    ephemeral=True
                )
                return

            # Ação
            if acao == "aprovar":
                await membro.edit(nick=self.nick)
                await membro.add_roles(self.cargo)
                registrar_recrutamento(guild.id, self.recrutador.id, membro.id)
                await interaction.response.edit_message(
                    content=f"✅ Solicitação aprovada por {interaction.user.mention}", view=None
                )
            elif acao == "rejeitar":
                await interaction.response.edit_message(
                    content=f"❌ Solicitação rejeitada por {interaction.user.mention}", view=None
                )

            # Log
            if self.config.get("canal_log_id"):
                canal_log = guild.get_channel(self.config["canal_log_id"])
                if canal_log:
                    cor = discord.Color.green() if acao == "aprovar" else discord.Color.red()
                    titulo = "📋 Recrutamento Aprovado" if acao == "aprovar" else "📋 Recrutamento Rejeitado"
                    embed_log = discord.Embed(title=titulo, color=cor)
                    embed_log.add_field(name="Usuário", value=membro.mention, inline=False)
                    embed_log.add_field(name="Nick", value=self.nick, inline=False)
                    embed_log.add_field(name="Telefone", value=self.tel, inline=False)
                    embed_log.add_field(name="Cargo", value=self.cargo.mention, inline=False)
                    embed_log.add_field(name="Recrutador", value=self.recrutador.mention, inline=False)
                    embed_log.add_field(name="Ação", value="Aprovado", inline=False)
                    embed_log.add_field(name="Responsável", value=interaction.user.mention, inline=False)
                    await canal_log.send(embed=embed_log)

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Não foi possível aplicar a ação (verifique a hierarquia de cargos).",
                ephemeral=True
            )
        finally:
            await asyncio.sleep(1)
            ConfirmacaoView.bloqueios.discard(membro.id)

    async def on_timeout(self):
        try:
            for child in self.children:
                child.disabled = True
            await self.message.edit(
                content="⌛ **Solicitação expirada** — ninguém aprovou ou rejeitou a tempo.",
                view=self
            )

            if self.config.get("canal_log_id"):
                guild = self.usuario.guild
                canal_log = guild.get_channel(self.config["canal_log_id"])
                if canal_log:
                    embed_log = discord.Embed(
                        title="⏰ Recrutamento Expirado",
                        description=f"A solicitação de set para {self.usuario.mention} expirou automaticamente.",
                        color=discord.Color.orange()
                    )
                    embed_log.add_field(name="Nick", value=self.nick, inline=False)
                    embed_log.add_field(name="Cargo", value=self.cargo.mention, inline=False)
                    embed_log.add_field(name="Recrutador", value=self.recrutador.mention, inline=False)
                    await canal_log.send(embed=embed_log)
        except Exception as e:
            print(f"[Erro Timeout] {e}")

    @button(label="✅ Aprovar", style=discord.ButtonStyle.green)
    async def aprovar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.processar(interaction, "aprovar")

    @button(label="❌ Rejeitar", style=discord.ButtonStyle.red)
    async def rejeitar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.processar(interaction, "rejeitar")


# -------------------- Ranking de Recrutadores --------------------


@bot.tree.command(name="ranking_de_rec", description="Mostra o ranking de quem recrutos mais.")
@app_commands.describe(periodo="Período: dia, semana ou mes")
async def ranking_recrutadores(interaction: discord.Interaction, periodo: str = "dia"):
    if periodo not in ["dia", "semana", "mes"]:
        await interaction.response.send_message("❌ Período inválido! Use: dia, semana ou mes.", ephemeral=True)
        return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    now = datetime.now()
    if periodo == "dia":
        data_inicio = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif periodo == "semana":
        data_inicio = now - timedelta(days=now.weekday())
        data_inicio = data_inicio.replace(
            hour=0, minute=0, second=0, microsecond=0)
    elif periodo == "mes":
        data_inicio = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0)

    c.execute("""
        SELECT recrutador_id, COUNT(*) as total
        FROM recrutamentos
        WHERE guild_id=? AND data >= ?
        GROUP BY recrutador_id
        ORDER BY total DESC
        LIMIT 10
    """, (str(interaction.guild.id), data_inicio))

    resultados = c.fetchall()
    conn.close()

    if not resultados:
        await interaction.response.send_message("⚠️ Nenhum recrutamento registrado nesse período.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"🏆 Ranking de Recrutadores ({periodo})", color=discord.Color.gold())
    for i, (recrutador_id, total) in enumerate(resultados, start=1):
        membro = interaction.guild.get_member(int(recrutador_id))
        nome = membro.display_name if membro else "Desconhecido"
        embed.add_field(
            name=f"{i}º lugar", value=f"{nome} — {total} recrutamentos", inline=False)

    await interaction.response.send_message(embed=embed)


# -------------------- View do botão de solicitação --------------------


class RecrutamentoView(View):
    def __init__(self, config):
        super().__init__(timeout=None)
        self.config = config

    @button(label="📋 Solicitar Recrutamento", style=discord.ButtonStyle.green)
    async def solicitar(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = self.config
        usuario = interaction.user
        guild = interaction.guild

        cargo_padrao = discord.utils.get(
            guild.roles, name=config["cargo_padrao"])
        cargo_crianca = discord.utils.get(
            guild.roles, name=config.get("cargo_crianca"))

        # 🔹 Bloqueia se o usuário tiver QUALQUER cargo além do @everyone
        # ou se já for Aprendiz / cargo_crianca
        for cargo in usuario.roles:
            if cargo != guild.default_role:  # ignora apenas @everyone
                await interaction.response.send_message(
                    f"⚠️ Você já possui o cargo {cargo.mention} e não pode solicitar setagem novamente.",
                    ephemeral=True
                )
                return

        # 🔹 Bloqueia se estiver registrado no banco (já recrutado)
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            "SELECT 1 FROM recrutamentos WHERE guild_id = ? AND usuario_id = ?",
            (str(guild.id), str(usuario.id))
        )
        ja_registrado = c.fetchone()
        conn.close()

        if ja_registrado:
            await interaction.response.send_message(
                "⚠️ Você já possui um registro de recrutamento ativo e não pode solicitar novamente.",
                ephemeral=True
            )
            return

        # 🔹 Monta seletor de recrutador
        membros = membros_com_permissao_dinamico(guild)
        options = [discord.SelectOption(
            label=m.display_name, value=str(m.id)) for m in membros
        ]

        if not options:
            await interaction.response.send_message(
                "⚠️ Nenhum recrutador disponível no momento.",
                ephemeral=True
            )
            return

        select = Select(
            placeholder="Escolha quem está te recrutando", options=options)

        async def callback(interaction2):
            recrutador_id = int(interaction2.data["values"][0])
            recrutador = guild.get_member(recrutador_id)
            await interaction2.response.send_modal(RecrutamentoModal(self.config, recrutador))

        select.callback = callback
        view = View()
        view.add_item(select)

        await interaction.response.send_message(
            "Escolha quem está te recrutando:", view=view, ephemeral=True
        )


# -------------------- Comandos de Slash --------------------

# Comando para configurar o recrutamento

@bot.tree.command(
    name="configuração",
    description="Configura o cargo, prefixos, canais e trabalho com crianças."
)
@app_commands.describe(
    trabalha_com_criancas="O servidor trabalha com crianças? (sim/não)",
    cargo="Cargo padrão",
    prefixo="Prefixo normal",
    cargo_crianca="Cargo específico para crianças (opcional)",
    prefixo_criancas="Prefixo para crianças (opcional)",
    canal_solicitacao="Canal onde os usuários solicitam setagem",
    canal_confirmacao="Canal onde as solicitações vão para aprovação",
    canal_log="Canal de log (opcional)"
)
async def configuracao(
    interaction: discord.Interaction,
    trabalha_com_criancas: str,
    cargo: discord.Role,                # ✅ Aceita menção direta do cargo
    prefixo: str,
    cargo_crianca: discord.Role = None, # ✅ Aceita menção direta
    prefixo_criancas: str = None,
    canal_solicitacao: discord.TextChannel = None,
    canal_confirmacao: discord.TextChannel = None,
    canal_log: discord.TextChannel = None
):
    # Checa se o usuário tem nível 0 ou 1
    if not checar_permissao_multiplos_niveis(interaction.user, [0, 1]):
        await interaction.response.send_message(
            "❌ Você não tem permissão para usar este comando.",
            ephemeral=True
        )
        return

    trabalha = normalizar_sim_nao(trabalha_com_criancas)
    if trabalha is None:
        await interaction.response.send_message(
            "❌ Valor inválido para 'trabalha_com_criancas'. Use sim ou não.",
            ephemeral=True
        )
        return

    if trabalha == "sim":
        if not cargo_crianca or not prefixo_criancas:
            await interaction.response.send_message(
                "❌ Para servidores que trabalham com crianças, `cargo_crianca` e `prefixo_criancas` são obrigatórios.",
                ephemeral=True
            )
            return

    # Salva a configuração no banco (usando .id para maior segurança)
    salvar_config(
        interaction.guild.id,
        cargo.name,  # salva o nome do cargo
        canal_solicitacao.id,
        canal_log.id if canal_log else None,
        prefixo,
        prefixo_criancas if trabalha == "sim" else "",
        trabalha,
        cargo_crianca.name if (trabalha == "sim" and cargo_crianca) else None,
        canal_confirmacao_id=canal_confirmacao.id if canal_confirmacao else None
    )

    # Mensagem de confirmação
    msg = f"✅ Configuração salva!\n**Cargo padrão**: `{cargo.name}`\n**Prefixo normal**: `{prefixo}`\n**Trabalha com crianças?**: {trabalha}"
    if trabalha == "sim":
        msg += f"\n**Cargo crianças**: `{cargo_crianca.name}`\n**Prefixo crianças**: `{prefixo_criancas}`"
    if canal_confirmacao:
        msg += f"\n**Canal de confirmação**: {canal_confirmacao.mention}"
    if canal_log:
        msg += f"\n**Canal de log**: {canal_log.mention}"

        # Aqui você continua com a lógica do comando
    embed = discord.Embed(
        title="⚙️ Configuração do Sistema de Recrutamento",
        description="Escolha a opção desejada abaixo:",
        color=discord.Color.green()
    )

    # Adicione campos com opções de configuração
    embed.add_field(
        name="Cargos",
        value="`/add_cargo_nivel` — Adiciona cargos aos níveis\n"
              "`/remover_cargo_nivel` — Remove cargos dos níveis",
        inline=False
    )
    embed.add_field(
        name="Canais",
        value="`/setar_canal_solicitacao` — Define o canal de solicitações\n"
              "`/setar_canal_log` — Define o canal de logs",
        inline=False
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)


# Comando para enviar o botão de recrutamento


@bot.tree.command(name="enviar_botao_recrutamento", description="Envia a mensagem com o botão de solicitação.")
async def enviar_botao_recrutamento(interaction: discord.Interaction):
    if not checar_permissao_multiplos_niveis(interaction.user, [0, 1, 2]):
        await interaction.response.send_message(
            "❌ Você não tem permissão para usar este comando.",
            ephemeral=True
        )
        return


    config = carregar_config(interaction.guild.id)
    if not config:
        await interaction.response.send_message("⚠️ Configure primeiro com `/configurar_recrutamento`.", ephemeral=True)
        return

    canal = interaction.guild.get_channel(config["canal_solicitacao_id"])
    view = RecrutamentoView(config)

    if config["mensagem_id"]:
        try:
            msg = await canal.fetch_message(config["mensagem_id"])
            await msg.pin()
            await interaction.response.send_message("✅ Mensagem já existente reapinada!", ephemeral=True)
            return
        except discord.NotFound:
            pass

    msg = await canal.send(config["mensagem_botao"], view=view)
    await msg.pin()
    salvar_config(interaction.guild.id, config["cargo_padrao"], config["canal_solicitacao_id"], config["canal_log_id"], config["prefixo"],
                  config["prefixo_criancas"], config["trabalha_com_criancas"], config["cargo_crianca"], mensagem_id=msg.id, mensagem_botao=config["mensagem_botao"], canal_confirmacao_id=config.get("canal_confirmacao_id"))
    await interaction.response.send_message("✅ Mensagem enviada e fixada com sucesso!", ephemeral=True)

# Comando para definir a mensagem acima do botão


@bot.tree.command(name="setar_mensagem_botao", description="Define a mensagem acima do botão de recrutamento.")
@app_commands.describe(mensagem="Texto da mensagem")
async def setar_mensagem_botao(interaction: discord.Interaction, mensagem: str):
    if not checar_permissao_multiplos_niveis(interaction.user, [0, 1, 2]):
        await interaction.response.send_message(
            "❌ Você não tem permissão para usar este comando.",
            ephemeral=True
        )
        return


    config = carregar_config(interaction.guild.id)
    if not config:
        await interaction.response.send_message("⚠️ Configure primeiro o recrutamento com `/configurar_recrutamento`.", ephemeral=True)
        return

    salvar_config(interaction.guild.id, config["cargo_padrao"], config["canal_solicitacao_id"], config["canal_log_id"], config["prefixo"],
                  config["prefixo_criancas"], config["trabalha_com_criancas"], config["cargo_crianca"], mensagem_id=config["mensagem_id"], mensagem_botao=mensagem, canal_confirmacao_id=config.get("canal_confirmacao_id"))
    await interaction.response.send_message(f"✅ Mensagem acima do botão atualizada:\n{mensagem}", ephemeral=True)

# Comandos para gerenciar cargos por nível

# Criar nível e associar cargo
@bot.tree.command(name="criar_nivel", description="Cria um nível de permissão no servidor")
@app_commands.describe(nivel="Número do nível", nome="Nome do nível")
async def cmd_criar_nivel(interaction: discord.Interaction, nivel: int, nome: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Apenas admins podem criar níveis.", ephemeral=True)
        return

    criar_nivel(interaction.guild.id, nivel, nome)
    await interaction.response.send_message(f"✅ Nível `{nome}` criado com sucesso!", ephemeral=True)


@bot.tree.command(name="atribuir_acao", description="Atribui uma ação a um nível")
@app_commands.describe(nivel="Número do nível", acao="Nome da ação")
async def cmd_atribuir_acao(interaction: discord.Interaction, nivel: int, acao: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Apenas admins podem atribuir ações.", ephemeral=True)
        return

    definir_acao_nivel(interaction.guild.id, nivel, acao)
    await interaction.response.send_message(f"✅ Ação `{acao}` atribuída ao nível {nivel}!", ephemeral=True)

# Adicionar cargo a nível existente
@bot.tree.command(name="add_cargo_nivel", description="Adiciona um cargo a um nível de permissão existente.")
@app_commands.describe(
    nivel="Nome do nível de permissão existente.",
    cargo="Cargo que deseja adicionar a esse nível."
)
async def add_cargo_nivel(interaction: discord.Interaction, nivel: str, cargo: discord.Role):
    # Verifica se o comando foi usado em um servidor
    if not interaction.guild:
        return await interaction.response.send_message("❌ Este comando só pode ser usado em servidores.", ephemeral=True)

    guild_id = interaction.guild.id
    cargo_id = cargo.id

    try:
        # Abre conexão com o banco de dados
        conn = sqlite3.connect("config.db")
        c = conn.cursor()

        # Verifica se o nível existe
        c.execute("SELECT 1 FROM niveis WHERE guild_id = ? AND nivel = ?", (guild_id, nivel))
        if not c.fetchone():
            conn.close()
            return await interaction.response.send_message(
                f"❌ O nível `{nivel}` não existe. Use `/criar_nivel` para criar um novo nível antes.",
                ephemeral=True
            )

        # Verifica se o cargo já está associado a esse nível
        c.execute("SELECT 1 FROM cargos_permissao WHERE guild_id = ? AND nivel = ? AND cargo_id = ?", (guild_id, nivel, cargo_id))
        if c.fetchone():
            conn.close()
            return await interaction.response.send_message(
                f"⚠️ O cargo {cargo.mention} **já está associado** ao nível `{nivel}`.",
                ephemeral=True
            )

        # Adiciona o cargo ao nível
        c.execute("INSERT INTO cargos_permissao (guild_id, nivel, cargo_id) VALUES (?, ?, ?)", (guild_id, nivel, cargo_id))
        conn.commit()
        conn.close()

        # Resposta de sucesso
        embed = discord.Embed(
            title="✅ Cargo adicionado ao nível",
            description=f"O cargo {cargo.mention} foi adicionado com sucesso ao nível **{nivel}**!",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Servidor: {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(f"❌ Erro ao adicionar o cargo: `{e}`", ephemeral=True)

# Remover cargo de nível
@bot.tree.command(name="remover_cargo_nivel", description="Remove um cargo de um nível de permissão existente.")
@app_commands.describe(
    nivel="Nome do nível do qual o cargo será removido.",
    cargo="Cargo que deseja remover desse nível."
)
async def remover_cargo_nivel(interaction: discord.Interaction, nivel: str, cargo: discord.Role):
    # Verifica se o comando foi usado em um servidor
    if not interaction.guild:
        return await interaction.response.send_message("❌ Este comando só pode ser usado em servidores.", ephemeral=True)

    guild_id = interaction.guild.id
    cargo_id = cargo.id

    try:
        # Abre conexão com o banco de dados
        conn = sqlite3.connect("config.db")
        c = conn.cursor()

        # Verifica se o nível existe
        c.execute("SELECT 1 FROM niveis WHERE guild_id = ? AND nivel = ?", (guild_id, nivel))
        if not c.fetchone():
            conn.close()
            return await interaction.response.send_message(
                f"❌ O nível `{nivel}` não existe. Use `/criar_nivel` para criar um novo nível.",
                ephemeral=True
            )

        # Verifica se o cargo está associado a esse nível
        c.execute("SELECT 1 FROM cargos_permissao WHERE guild_id = ? AND nivel = ? AND cargo_id = ?", (guild_id, nivel, cargo_id))
        if not c.fetchone():
            conn.close()
            return await interaction.response.send_message(
                f"⚠️ O cargo {cargo.mention} **não está associado** ao nível `{nivel}`.",
                ephemeral=True
            )

        # Remove o cargo do nível
        c.execute("DELETE FROM cargos_permissao WHERE guild_id = ? AND nivel = ? AND cargo_id = ?", (guild_id, nivel, cargo_id))
        conn.commit()
        conn.close()

        # Resposta de sucesso
        embed = discord.Embed(
            title="✅ Cargo removido do nível",
            description=f"O cargo {cargo.mention} foi removido do nível **{nivel}** com sucesso!",
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Servidor: {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(f"❌ Erro ao remover o cargo: `{e}`", ephemeral=True)

# Remover cadastro de recrutamento
@bot.tree.command(name="remover_cadastro", description="Remove uma pessoa do cadastro de recrutamentos.")
@app_commands.describe(
    membro="Selecione o membro a ser removido do cadastro."
)
async def remover_cadastro(interaction: discord.Interaction, membro: discord.Member):
    # Verifica se o comando foi usado em um servidor
    if not interaction.guild:
        return await interaction.response.send_message("❌ Este comando só pode ser usado em servidores.", ephemeral=True)

    guild_id = interaction.guild.id
    user_id = membro.id

    try:
        # --- 🔒 Verifica permissão dinâmica (baseada nos níveis configurados) ---
        conn = sqlite3.connect("config.db")
        c = conn.cursor()
        c.execute("SELECT nivel, cargo_id FROM cargos_permissao WHERE guild_id = ?", (guild_id,))
        permissoes = c.fetchall()

        if not permissoes:
            conn.close()
            return await interaction.response.send_message(
                "⚠️ Nenhum cargo de permissão foi configurado ainda. Use `/add_cargo_nivel` antes.",
                ephemeral=True
            )

        # Obtém IDs de cargos autorizados
        cargos_autorizados = [cargo_id for _, cargo_id in permissoes]

        # Verifica se o autor tem algum dos cargos
        if not any(role.id in cargos_autorizados for role in interaction.user.roles):
            conn.close()
            return await interaction.response.send_message(
                "🚫 Você **não tem permissão** para remover cadastros.",
                ephemeral=True
            )

        # --- 🔍 Verifica se o membro está cadastrado ---
        c.execute("SELECT * FROM recrutamentos WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        registro = c.fetchone()

        if not registro:
            conn.close()
            return await interaction.response.send_message(
                f"⚠️ O membro {membro.mention} **não está cadastrado** no sistema.",
                ephemeral=True
            )

        # --- 🗑️ Remove o registro ---
        c.execute("DELETE FROM recrutamentos WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        conn.commit()

        # Busca o cargo de recrutado para remover
        c.execute("SELECT cargo_recruta FROM config WHERE guild_id = ?", (guild_id,))
        resultado = c.fetchone()
        conn.close()

        # Cria o embed de confirmação
        embed = discord.Embed(
            title="🗑️ Cadastro removido",
            description=f"O membro {membro.mention} foi **removido do cadastro** com sucesso!",
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Servidor: {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)

        await interaction.response.send_message(embed=embed, ephemeral=True)

        # --- 🎭 Remove o cargo do membro (se configurado) ---
        if resultado and resultado[0]:
            cargo_recruta_id = int(resultado[0])
            cargo = interaction.guild.get_role(cargo_recruta_id)
            if cargo and cargo in membro.roles:
                try:
                    await membro.remove_roles(cargo)
                except discord.Forbidden:
                    await interaction.followup.send(
                        f"⚠️ Não consegui remover o cargo {cargo.mention} de {membro.mention}. Verifique minhas permissões.",
                        ephemeral=True
                    )

        # --- 🪵 Loga a ação (se canal de logs configurado) ---
        conn = sqlite3.connect("config.db")
        c = conn.cursor()
        c.execute("SELECT canal_logs FROM config WHERE guild_id = ?", (guild_id,))
        log_result = c.fetchone()
        conn.close()

        if log_result and log_result[0]:
            canal_logs_id = int(log_result[0])
            canal_logs = interaction.guild.get_channel(canal_logs_id)
            if canal_logs:
                log_embed = discord.Embed(
                    title="📋 Remoção de Cadastro",
                    description=f"**Recrutado removido:** {membro.mention}\n**Removido por:** {interaction.user.mention}",
                    color=discord.Color.orange()
                )
                log_embed.timestamp = discord.utils.utcnow()
                await canal_logs.send(embed=log_embed)

    except Exception as e:
        await interaction.response.send_message(f"❌ Erro ao remover o cadastro: `{e}`", ephemeral=True)


# Listar cadastros de recrutamento
@bot.tree.command(name="listar_cadastros", description="Mostra todos os membros cadastrados ou apenas os de um recrutador específico.")
@app_commands.describe(recrutador="Mencione o recrutador para filtrar os cadastros (opcional)")
async def listar_cadastros(interaction: discord.Interaction, recrutador: discord.Member = None):
    if not interaction.guild:
        return await interaction.response.send_message("❌ Este comando só pode ser usado em servidores.", ephemeral=True)

    guild_id = interaction.guild.id

    try:
        # --- 🔒 Verificação de permissão dinâmica ---
        conn = sqlite3.connect("config.db")
        c = conn.cursor()
        c.execute("SELECT cargo_id FROM cargos_permissao WHERE guild_id = ?", (guild_id,))
        permissoes = [cargo_id for (cargo_id,) in c.fetchall()]

        if not permissoes:
            conn.close()
            return await interaction.response.send_message(
                "⚠️ Nenhum cargo de permissão foi configurado. Use `/add_cargo_nivel` para configurar.",
                ephemeral=True
            )

        if not any(role.id in permissoes for role in interaction.user.roles):
            conn.close()
            return await interaction.response.send_message(
                "🚫 Você **não tem permissão** para listar cadastros.",
                ephemeral=True
            )

        # --- 📋 Obtém os cadastros ---
        if recrutador:
            c.execute("""
                SELECT user_id, nome, nick, recrutador_id, data 
                FROM recrutamentos 
                WHERE guild_id = ? AND recrutador_id = ?
                ORDER BY data DESC
            """, (guild_id, recrutador.id))
        else:
            c.execute("""
                SELECT user_id, nome, nick, recrutador_id, data 
                FROM recrutamentos 
                WHERE guild_id = ?
                ORDER BY data DESC
            """, (guild_id,))

        registros = c.fetchall()
        conn.close()

        if not registros:
            if recrutador:
                return await interaction.response.send_message(
                    f"📭 Nenhum cadastro encontrado para {recrutador.mention}.",
                    ephemeral=True
                )
            else:
                return await interaction.response.send_message(
                    "📭 Nenhum recrutamento encontrado neste servidor.",
                    ephemeral=True
                )

        # --- 📄 Paginação ---
        por_pagina = 5
        paginas = [registros[i:i + por_pagina] for i in range(0, len(registros), por_pagina)]
        total_paginas = len(paginas)

        def gerar_embed(pagina_idx: int):
            titulo = "📋 Cadastros"
            if recrutador:
                titulo += f" de {recrutador.display_name}"

            embed = discord.Embed(
                title=titulo,
                description=f"Página {pagina_idx + 1}/{total_paginas}",
                color=discord.Color.blurple()
            )

            for user_id, nome, nick, recrutador_id, data in paginas[pagina_idx]:
                recrutador_info = interaction.guild.get_member(recrutador_id)
                membro = interaction.guild.get_member(user_id)
                embed.add_field(
                    name=f"{nome or 'Sem nome'} ({nick or 'Sem nick'})",
                    value=f"👤 **Membro:** {membro.mention if membro else f'ID {user_id}'}\n"
                          f"🎯 **Recrutador:** {recrutador_info.mention if recrutador_info else f'ID {recrutador_id}'}\n"
                          f"📅 **Data:** {data}",
                    inline=False
                )

            embed.set_footer(text=f"Total de registros: {len(registros)}")
            return embed

        # --- 🔘 View com botões de navegação ---
        class PaginacaoView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=180)
                self.pagina_atual = 0

            async def atualizar(self, interaction_update):
                embed = gerar_embed(self.pagina_atual)
                await interaction_update.response.edit_message(embed=embed, view=self)

            @discord.ui.button(label="⏮️", style=discord.ButtonStyle.gray)
            async def inicio(self, interaction_button, _):
                self.pagina_atual = 0
                await self.atualizar(interaction_button)

            @discord.ui.button(label="⬅️", style=discord.ButtonStyle.blurple)
            async def anterior(self, interaction_button, _):
                if self.pagina_atual > 0:
                    self.pagina_atual -= 1
                    await self.atualizar(interaction_button)

            @discord.ui.button(label="➡️", style=discord.ButtonStyle.blurple)
            async def proxima(self, interaction_button, _):
                if self.pagina_atual < total_paginas - 1:
                    self.pagina_atual += 1
                    await self.atualizar(interaction_button)

            @discord.ui.button(label="⏭️", style=discord.ButtonStyle.gray)
            async def fim(self, interaction_button, _):
                self.pagina_atual = total_paginas - 1
                await self.atualizar(interaction_button)

        view = PaginacaoView()
        await interaction.response.send_message(embed=gerar_embed(0), view=view, ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(f"❌ Erro ao listar cadastros: `{e}`", ephemeral=True)


# Listar todos os níveis e cargos
@bot.tree.command(name="listar_niveis", description="Mostra todos os níveis e cargos configurados no servidor.")
async def listar_niveis(interaction: discord.Interaction):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT nivel, cargo_nome FROM cargos_permissao WHERE guild_id=? ORDER BY nivel", (str(interaction.guild.id),))
    resultados = c.fetchall()
    conn.close()
    if not resultados:
        await interaction.response.send_message("⚠️ Nenhum nível configurado.", ephemeral=True)
        return
    msg = ""
    for nivel, cargo in resultados:
        msg += f"**Nível {nivel}** → {cargo}\n"
    await interaction.response.send_message(msg, ephemeral=True)


@bot.tree.command(
    name="configurar_tempo_expiracao",
    description="Define o tempo (em minutos) até que uma solicitação de set expire automaticamente."
)
@app_commands.describe(minutos="Tempo em minutos (1-120)")
async def configurar_tempo_expiracao(interaction: discord.Interaction, minutos: int):
    if not checar_permissao_multiplos_niveis(interaction.user, 0):
        await interaction.response.send_message(
            "❌ Você não tem permissão para usar este comando.",
            ephemeral=True
        )
        return

    if minutos < 1 or minutos > 120:
        await interaction.response.send_message(
            "⚠️ O tempo deve estar entre **1** e **120 minutos**.",
            ephemeral=True
        )
        return

    guild_id = str(interaction.guild.id)

    # 🔹 Atualiza memória
    if guild_id not in config_global:
        config_global[guild_id] = {}
    config_global[guild_id]["tempo_expiracao"] = minutos

    # 🔹 Atualiza banco de dados
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        UPDATE config
        SET tempo_expiracao = ?
        WHERE guild_id = ?
    """, (minutos, guild_id))
    conn.commit()
    conn.close()

    await interaction.response.send_message(
        f"⏰ Tempo de expiração definido para **{minutos} minutos**.",
        ephemeral=True
    )



# ==============================
# 🧭 PAINEL DE CONTROLE INTERATIVO
# ==============================


class PainelView(discord.ui.View):
    def __init__(self, nivel_usuario: int):
        super().__init__(timeout=None)
        self.nivel_usuario = nivel_usuario

        # Adiciona os botões com base no nível do usuário
        if nivel_usuario == 0:
            self.add_item(discord.ui.Button(label="⚙️ Configurações",
                          style=discord.ButtonStyle.primary, custom_id="config"))
            self.add_item(discord.ui.Button(
                label="📊 Relatórios", style=discord.ButtonStyle.success, custom_id="relatorio"))
            self.add_item(discord.ui.Button(
                label="🎨 Visual", style=discord.ButtonStyle.secondary, custom_id="visual"))
        elif nivel_usuario == 1:
            self.add_item(discord.ui.Button(
                label="📊 Relatórios", style=discord.ButtonStyle.success, custom_id="relatorio"))
            self.add_item(discord.ui.Button(
                label="🎨 Visual", style=discord.ButtonStyle.secondary, custom_id="visual"))
        elif nivel_usuario == 2:
            self.add_item(discord.ui.Button(
                label="🎨 Visual", style=discord.ButtonStyle.secondary, custom_id="visual"))

    @discord.ui.button(label="🧭 Atualizar painel", style=discord.ButtonStyle.gray, row=1)
    async def atualizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await comando_painel(interaction)

    async def interaction_check(self, interaction: discord.Interaction):
        return True

# ===============================
# Funções de níveis e ações
# ===============================
def niveis_disponiveis_guild(guild_id: int):
    """Retorna todos os níveis configurados no servidor."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT DISTINCT nivel FROM niveis WHERE guild_id=? ORDER BY nivel ASC",
        (str(guild_id),)
    )
    niveis = [row[0] for row in c.fetchall()]
    conn.close()
    return niveis


def obter_acoes_nivel(guild_id: int, nivel: int):
    """Retorna as ações disponíveis para um nível."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT acao FROM acoes_por_nivel WHERE guild_id=? AND nivel=?",
        (str(guild_id), nivel)
    )
    resultados = [row[0] for row in c.fetchall()]
    conn.close()
    return resultados


# ===============================
# Painel dinâmico
# ===============================
async def exibir_painel(interaction: discord.Interaction):
    user = interaction.user
    guild_id = interaction.guild.id

    # Detecta o nível mais alto do usuário
    nivel_usuario = None
    for nivel in reversed(niveis_disponiveis_guild(guild_id)):
        if checar_permissao_multiplos_niveis(user, nivel):
            nivel_usuario = nivel
            break

    if nivel_usuario is None:
        await interaction.response.send_message(
            "🔒 Você não possui nenhum nível de permissão configurado.",
            ephemeral=True
        )
        return

    # Cria o embed
    embed = discord.Embed(
        title=f"🧭 Painel de Controle (Nível {nivel_usuario})",
        description="Selecione uma das opções abaixo para ver seus comandos disponíveis.",
        color=discord.Color.blue()
    )

    # Adiciona campos dinamicamente de acordo com as ações do nível
    acoes = obter_acoes_nivel(guild_id, nivel_usuario)
    if "configuracao" in acoes:
        embed.add_field(
            name="⚙️ Configurações",
            value="Comandos de configuração do sistema e níveis",
            inline=False
        )
    if "relatorios" in acoes:
        embed.add_field(
            name="📊 Relatórios",
            value="Comandos de ranking e relatórios",
            inline=False
        )
    if "visual" in acoes:
        embed.add_field(
            name="🎨 Visual",
            value="Comandos para botão de recrutamento e mensagens",
            inline=False
        )

    # Exibe o painel
    await interaction.response.send_message(embed=embed, view=PainelView(nivel_usuario), ephemeral=True)


# ===============================
# Comando /painel
# ===============================
@bot.tree.command(
    name="painel",
    description="Mostra o painel de controle conforme seu nível de permissão."
)
async def comando_painel(interaction: discord.Interaction):
    await exibir_painel(interaction)


# ===============================
# View dos botões
# ===============================
class PainelView(View):
    def __init__(self, nivel_usuario: int):
        super().__init__(timeout=None)
        self.nivel_usuario = nivel_usuario

    @button(label="🔁 Atualizar Painel", style=discord.ButtonStyle.blurple)
    async def atualizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await exibir_painel(interaction)
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Erro ao atualizar painel: {e}",
                ephemeral=True
            )

# -------------------- Recriação automática da mensagem de recrutamento --------------------
@bot.event
async def on_message_delete(message: discord.Message):
    # Garante que é o bot que mandou a mensagem
    if not message.author.bot:
        return

    try:
        config = carregar_config(message.guild.id)
        if not config:
            return

        # Confere se a mensagem apagada é o botão de recrutamento
        if config.get("mensagem_id") and message.id == config["mensagem_id"]:
            canal = message.guild.get_channel(config["canal_solicitacao_id"])
            if canal:
                view = RecrutamentoView(config)
                msg = await canal.send(config["mensagem_botao"], view=view)
                await msg.pin()

                # Atualiza o novo ID da mensagem recriada
                salvar_config(
                    message.guild.id,
                    config["cargo_padrao"],
                    config["canal_solicitacao_id"],
                    config["canal_log_id"],
                    config["prefixo"],
                    config["prefixo_criancas"],
                    config["trabalha_com_criancas"],
                    config["cargo_crianca"],
                    mensagem_id=msg.id,
                    mensagem_botao=config["mensagem_botao"],
                    canal_confirmacao_id=config.get("canal_confirmacao_id")
                )

                print(
                    f"🔁 Mensagem de recrutamento recriada automaticamente em {canal.name}")

    except Exception as e:
        print(f"❌ Erro ao recriar mensagem de recrutamento: {e}")

# Inicie o servidor web e o bot
keep_alive()
bot.run(TOKEN)


