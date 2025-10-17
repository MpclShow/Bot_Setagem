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
# from dotenv import load_dotenv

config_global = {}

# Adicione esta lista na parte superior do seu arquivo, perto de 'config_global'
ACOES_DISPONIVEIS = [
    "configuracao",  # Acesso ao comando /configuracao
    "relatorios",    # Acesso a /ranking_de_rec, /listar_cadastros, /remover_cadastro
    "visual",        # Acesso a /enviar_botao_recrutamento, /setar_mensagem_botao
    "atribuicao_acao", # Acesso a /atribuir_acao
    "gerenciamento_nivel" # Acesso a /criar_nivel, /add_cargo_nivel, /remover_cargo_nivel
]


# --- Mantenha o bot online ---

app = Flask('')


@app.route('/')
def main():
    return "O bot está online! ver. 0.0.3"


def run():
    app.run(host="0.0.0.0", port=8080)


def keep_alive():
    server = Thread(target=run)
    server.start()
# -----------------------------

# load_dotenv()
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
    # Ajustado para usar cargo_nome conforme a implementação original do checar_permissao_multiplos_niveis
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
        with sqlite3.connect(DB_FILE) as conn:
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

    # Otimização: buscar todos os nomes de cargos autorizados de uma vez
    cargos_autorizados_nomes = set()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for nivel in niveis:
        c.execute(
            "SELECT cargo_nome FROM cargos_permissao WHERE guild_id=? AND nivel=?",
            (str(guild.id), nivel)
        )
        cargos_autorizados_nomes.update([row[0] for row in c.fetchall()])
    conn.close()

    if not cargos_autorizados_nomes:
        return []

    # Otimização: verificar apenas os cargos do membro
    for membro in guild.members:
        membro_cargos_nomes = {role.name for role in membro.roles}
        if any(cargo_nome in membro_cargos_nomes for cargo_nome in cargos_autorizados_nomes):
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
    print("O bot está online! ver. 0.0.3")


# --- NOVAS CLASSES PARA O COMANDO /atribuir_acao ---

class AcaoSelect(Select):
    """Menu de seleção que permite múltiplas escolhas de ações."""
    def __init__(self, nivel_escolhido: int, guild_id: str):
        
        # 1. Obtém as ações já definidas para este nível
        self.acoes_atuais = obter_acoes_nivel(guild_id, nivel_escolhido)
        self.nivel = nivel_escolhido
        self.guild_id = guild_id
        
        options = []
        for acao in ACOES_DISPONIVEIS:
            # Marca como padrão se já estiver definida para o nível
            is_default = acao in self.acoes_atuais
            options.append(discord.SelectOption(
                label=acao.capitalize().replace("_", " "),
                value=acao,
                default=is_default,
                description="Já configurada" if is_default else "Ação disponível"
            ))
            
        super().__init__(
            placeholder=f"Selecione as ações para o Nível {nivel_escolhido}",
            min_values=0, # Permite desmarcar todas as ações
            max_values=len(ACOES_DISPONIVEIS),
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        # As ações selecionadas são passadas em self.values
        acoes_selecionadas = set(self.values)
        
        # 1. Ações a adicionar (Selecionadas, mas não atuais)
        acoes_a_adicionar = acoes_selecionadas - set(self.acoes_atuais)
        for acao in acoes_a_adicionar:
            definir_acao_nivel(self.guild_id, self.nivel, acao)
            
        # 2. Ações a remover (Atuais, mas não selecionadas)
        acoes_a_remover = set(self.acoes_atuais) - acoes_selecionadas
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        for acao in acoes_a_remover:
            c.execute(
                "DELETE FROM acoes_por_nivel WHERE guild_id=? AND nivel=? AND acao=?",
                (self.guild_id, self.nivel, acao)
            )
        conn.commit()
        conn.close()
        
        # Cria a mensagem de resultado
        embed = discord.Embed(
            title=f"✅ Ações atualizadas para o Nível {self.nivel}",
            color=discord.Color.green()
        )
        if acoes_a_adicionar:
            embed.add_field(name="Adicionadas", value="\n".join([f"➕ `{a}`" for a in acoes_a_adicionar]), inline=False)
        if acoes_a_remover:
            embed.add_field(name="Removidas", value="\n".join([f"➖ `{a}`" for a in acoes_a_remover]), inline=False)
        if not acoes_a_adicionar and not acoes_a_remover:
            embed.description = "Nenhuma alteração foi feita."

        # Edita a mensagem original com o resultado e o novo seletor
        # (Chama o seletor novamente para refletir as ações atuais)
        nova_view = AcaoNivelView(self.nivel, interaction.guild.id)
        
        await interaction.response.edit_message(
            content=f"Selecione as ações para o Nível **{self.nivel}**:",
            embed=embed,
            view=nova_view
        )


class AcaoNivelView(View):
    """View que contém o menu de seleção de ações."""
    def __init__(self, nivel: int, guild_id: int):
        super().__init__(timeout=180)
        # Adiciona o seletor na view
        self.add_item(AcaoSelect(nivel, str(guild_id)))

# -------------------- Modal de Solicitação --------------------

# MODIFICAÇÃO 1/3: RecrutamentoModal ajustada para receber cargo/prefixo pré-definidos.
class RecrutamentoModal(Modal, title="📋 Solicitação de Recrutamento"):
    def __init__(self, config, recrutador_member: discord.Member, cargo: discord.Role, prefixo_usado: str):
        super().__init__()
        self.config = config
        self.recrutador_member = recrutador_member
        self.cargo = cargo
        self.prefixo_usado = prefixo_usado
        
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
        
        cargo = self.cargo
        prefixo_usado = self.prefixo_usado
        
        if not cargo:
            await interaction.response.send_message(f"❌ Cargo necessário não encontrado.", ephemeral=True)
            return

        # Busca canal de confirmação
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
            else:
                await interaction.response.send_message(f"✅ Sua solicitação foi enviada para o recrutador!", ephemeral=True)
        # Se não houver canal de confirmação, confirma ao usuário
        else:
             await interaction.response.send_message(f"✅ Sua solicitação foi enviada para o recrutador!", ephemeral=True)
        
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

    # 🚨 BOTÃO 1: APROVAR 🚨
    @discord.ui.button(label="✅ Aprovar", style=discord.ButtonStyle.green, custom_id="aprov_recrutamento")
    async def aprovar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Desabilita todos os botões imediatamente para evitar cliques duplos
        self.stop() 
        await self.processar(interaction, "aprovar")

    # 🚨 BOTÃO 2: REJEITAR 🚨
    @discord.ui.button(label="❌ Rejeitar", style=discord.ButtonStyle.red, custom_id="rejeitar_recrutamento")
    async def rejeitar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Desabilita todos os botões imediatamente para evitar cliques duplos
        self.stop()
        await self.processar(interaction, "rejeitar")

    async def processar(self, interaction: discord.Interaction, acao: str):
        guild = interaction.guild
        membro = self.usuario

        # --- Verificação de Bloqueio (Primeira Resposta) ---
        if membro.id in ConfirmacaoView.bloqueios:
            # Envia a mensagem de erro e retorna (Única resposta)
            await interaction.response.send_message(
                "⚠️ Já existe uma ação em andamento para este recrutamento.",
                ephemeral=True
            )
            return
        ConfirmacaoView.bloqueios.add(membro.id)

        try:
            # --- Verificação de Permissão (Primeira Resposta) ---
            if not checar_permissao_multiplos_niveis(interaction.user, [0, 1]):
                await interaction.response.send_message(
                    f"❌ Você não tem permissão para {acao}.",
                    ephemeral=True
                )
                return # Termina a função após a resposta

            # --- Verificação de Autoação (Primeira Resposta) ---
            if interaction.user.id == self.usuario.id:
                await interaction.response.send_message(
                    f"⚠️ Você não pode {acao} a si mesmo.",
                    ephemeral=True
                )
                if self.config.get("canal_log_id"):
                    # Se você quer logar, use followup.send, pois a response já foi usada
                    canal_log = guild.get_channel(self.config["canal_log_id"])
                    if canal_log:
                        embed_log = discord.Embed(
                            title="🚫 Tentativa de autoação bloqueada",
                            description=f"{interaction.user.mention} tentou {acao} a própria solicitação.",
                            color=discord.Color.orange()
                        )
                        # Usa followup.send, pois response.send_message já foi chamado acima
                        await interaction.followup.send(embed=embed_log, ephemeral=False)
                return # Termina a função após a resposta

            cargo_padrao = discord.utils.get(
                guild.roles, name=self.config["cargo_padrao"])
            cargo_crianca = discord.utils.get(
                guild.roles, name=self.config.get("cargo_crianca"))
            
            # --- Verificação de Já Setado (Primeira Resposta) ---
            if membro is None or (cargo_padrao and cargo_padrao in membro.roles) or (cargo_crianca and cargo_crianca in membro.roles):
                await interaction.response.send_message(
                    f"⚠️ O membro {membro.mention if membro else 'N/A'} já está setado ou não existe.",
                    ephemeral=True
                )
                return # Termina a função após a resposta

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute(
                "SELECT 1 FROM recrutamentos WHERE guild_id=? AND usuario_id=?",
                (str(guild.id), str(membro.id))
            )
            ja_registrado = c.fetchone()
            conn.close()

            # --- Verificação de Já Registrado (Primeira Resposta) ---
            if ja_registrado and acao == "aprovar":
                await interaction.response.send_message(
                    f"⚠️ O membro {membro.mention} já possui um registro de recrutamento.",
                    ephemeral=True
                )
                return # Termina a função após a resposta

            # --- AÇÃO DE SUCESSO (Resposta Única: Edita a mensagem) ---
            if acao == "aprovar":
                await membro.edit(nick=self.nick)
                await membro.add_roles(self.cargo)
                registrar_recrutamento(guild.id, self.recrutador.id, membro.id)
                # AQUI ESTÁ A RESPOSTA DE EDIÇÃO DE SUCESSO
                await interaction.response.edit_message(
                    content=f"✅ Solicitação aprovada por {interaction.user.mention}", view=None
                )
            elif acao == "rejeitar":
                 # AQUI ESTÁ A RESPOSTA DE EDIÇÃO DE SUCESSO
                await interaction.response.edit_message(
                    content=f"❌ Solicitação rejeitada por {interaction.user.mention}", view=None
                )
            
            # --- Log (Usa Followup se a resposta já foi dada) ---
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
                    embed_log.add_field(name="Ação", value="Aprovado" if acao == "aprovar" else "Rejeitado", inline=False)
                    embed_log.add_field(name="Responsável", value=interaction.user.mention, inline=False)
                    await canal_log.send(embed=embed_log) # Não precisa de followup/response aqui, é apenas uma nova mensagem.


        except discord.Forbidden:
            # Se a resposta ainda não foi dada, envia uma resposta de erro.
            # Caso contrário, usa followup para garantir a resposta.
            if interaction.response.is_done():
                 await interaction.followup.send(
                    "❌ Não foi possível aplicar a ação (verifique a hierarquia de cargos).",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ Não foi possível aplicar a ação (verifique a hierarquia de cargos).",
                    ephemeral=True
                )
        except Exception as e:
            # Mesma lógica para qualquer outro erro.
            if interaction.response.is_done():
                await interaction.followup.send(
                    f"❌ Erro inesperado ao processar: {e}",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ Erro inesperado ao processar: {e}",
                    ephemeral=True
                )
        finally:
            await asyncio.sleep(1)
            ConfirmacaoView.bloqueios.discard(membro.id)


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

# MODIFICAÇÃO 2/3: RecrutamentoView ajustada para incluir o seletor de criança.
class RecrutamentoView(View):
    def __init__(self, config):
        super().__init__(timeout=None)
        self.config = config

    @button(label="📋 Solicitar Recrutamento", style=discord.ButtonStyle.green)
    async def solicitar(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = self.config
        usuario = interaction.user
        guild = interaction.guild

        # --- Verificações Iniciais ---
        
        # 🔹 Bloqueia se o usuário tiver QUALQUER cargo além do @everyone
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

        # --- Fluxo de Seleção de Recrutador ---
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
        
        
        # -----------------------------------------------
        # ⚙️ FUNÇÕES AUXILIARES PARA FLUXO DE SELEÇÃO
        # -----------------------------------------------
        
        # Função que define o cargo/prefixo e abre o modal
        async def abrir_modal_recrutamento(interaction_orig: discord.Interaction, recrutador: discord.Member, eh_crianca: str):
            
            cargo_padrao_role = discord.utils.get(guild.roles, name=config["cargo_padrao"])
            cargo_crianca_role = discord.utils.get(guild.roles, name=config.get("cargo_crianca"))

            if eh_crianca == "sim" and normalizar_sim_nao(config["trabalha_com_criancas"]) == "sim" and cargo_crianca_role:
                cargo_final = cargo_crianca_role
                prefixo_final = config.get("prefixo_criancas", config.get("prefixo", "APR"))
            else:
                cargo_final = cargo_padrao_role
                prefixo_final = config.get("prefixo", "APR")
                
            if not cargo_final:
                await interaction_orig.response.send_message("❌ Cargo padrão ou de criança não configurado.", ephemeral=True)
                return

            modal = RecrutamentoModal(config, recrutador, cargo_final, prefixo_final)
            await interaction_orig.response.send_modal(modal)


        # Função que exibe a pergunta sobre ser criança (Se necessário)
        async def selecionar_crianca(interaction_recrutador: discord.Interaction, recrutador: discord.Member):
            
            select_crianca = Select(
                placeholder="Você trabalha como criança (Menor de 14)?",
                options=[
                    discord.SelectOption(label="Sim", value="sim", description="Para quem tem menos de 14 anos."),
                    discord.SelectOption(label="Não", value="nao", description="Para quem tem 14 anos ou mais."),
                ]
            )

            async def callback_crianca(interaction_crianca):
                eh_crianca = interaction_crianca.data["values"][0]
                await abrir_modal_recrutamento(interaction_crianca, recrutador, eh_crianca)

            select_crianca.callback = callback_crianca
            view_crianca = View(timeout=180)
            view_crianca.add_item(select_crianca)
            
            await interaction_recrutador.response.edit_message(
                content="✅ Recrutador escolhido! Agora, confirme se você trabalha como criança:",
                view=view_crianca
            )
        
        # Função que processa a escolha do recrutador
        async def callback_recrutador(interaction_recrutador):
            recrutador_id = int(interaction_recrutador.data["values"][0])
            recrutador = guild.get_member(recrutador_id)
            
            # --- Se o servidor trabalha com crianças, abre o seletor de criança ---
            if normalizar_sim_nao(config["trabalha_com_criancas"]) == "sim" and config.get("cargo_crianca"):
                await selecionar_crianca(interaction_recrutador, recrutador)
            # --- Caso contrário, abre o modal de recrutamento direto com cargo padrão ---
            else:
                await abrir_modal_recrutamento(interaction_recrutador, recrutador, eh_crianca="nao")

        # --- Exibir o seletor de recrutador ---
        
        select_recrutador = Select(
            placeholder="Escolha quem está te recrutando", options=options)
        select_recrutador.callback = callback_recrutador
        
        view_recrutador = View(timeout=180)
        view_recrutador.add_item(select_recrutador)

        await interaction.response.send_message(
            "Escolha quem está te recrutando:", view=view_recrutador, ephemeral=True
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
    cargo: discord.Role,               
    prefixo: str,
    cargo_crianca: discord.Role = None, 
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

    embed = discord.Embed(
        title="⚙️ Configuração do Sistema de Recrutamento",
        description=msg,
        color=discord.Color.green()
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
        await interaction.response.send_message("⚠️ Configure primeiro com `/configuração`.", ephemeral=True)
        return

    canal = interaction.guild.get_channel(config["canal_solicitacao_id"])
    
    if not canal:
         await interaction.response.send_message("⚠️ O canal de solicitação não foi encontrado. Verifique a configuração com `/configuração`.", ephemeral=True)
         return
         
    view = RecrutamentoView(config)

    if config["mensagem_id"]:
        try:
            msg = await canal.fetch_message(config["mensagem_id"])
            await msg.pin()
            await interaction.response.send_message("✅ Mensagem já existente reapinada!", ephemeral=True)
            return
        except discord.NotFound:
            pass # Mensagem não encontrada, enviaremos uma nova

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
        await interaction.response.send_message("⚠️ Configure primeiro o recrutamento com `/configuração`.", ephemeral=True)
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
    await interaction.response.send_message(f"✅ Nível `{nivel}` criado com o nome `{nome}`!", ephemeral=True)


# --- MODIFICAÇÃO DO COMANDO /atribuir_acao ---

@bot.tree.command(name="atribuir_acao", description="Abre um painel para gerenciar quais ações pertencem a um nível.")
async def cmd_atribuir_acao(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Apenas admins podem atribuir ações.", ephemeral=True)
        return

    guild_id = interaction.guild.id
    
    # 1. Obtém os níveis disponíveis para o primeiro Select
    niveis = niveis_disponiveis(guild_id)
    if not niveis:
        await interaction.response.send_message("⚠️ Nenhum nível criado. Use `/criar_nivel` primeiro.", ephemeral=True)
        return

    # 2. Cria o Select para escolher o Nível
    options_niveis = [
        discord.SelectOption(label=f"Nível {n}", value=str(n)) for n in sorted(niveis)
    ]

    select_nivel = Select(
        placeholder="Escolha o nível para editar as ações...",
        options=options_niveis,
        min_values=1,
        max_values=1
    )

    async def callback_nivel(interaction_nivel):
        nivel_escolhido = int(interaction_nivel.data['values'][0])
        
        # 3. Após escolher o nível, exibe o Multi-Select de ações
        view_acoes = AcaoNivelView(nivel_escolhido, guild_id)
        
        # Obtém o nome do nível para a mensagem (se estiver configurado)
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT nome FROM niveis WHERE guild_id=? AND nivel=?", (str(guild_id), nivel_escolhido))
        nome_nivel = c.fetchone()
        conn.close()
        nome_display = f"{nome_nivel[0]}" if nome_nivel else f"Nível {nivel_escolhido}"


        await interaction_nivel.response.edit_message(
            content=f"🛠️ Gerenciando ações para **{nome_display}**.",
            embed=None,
            view=view_acoes
        )

    select_nivel.callback = callback_nivel
    view_inicial = View(timeout=180)
    view_inicial.add_item(select_nivel)

    await interaction.response.send_message("Primeiro, escolha o Nível que deseja configurar:", view=view_inicial, ephemeral=True)
# Adicionar cargo a nível existente
@bot.tree.command(name="add_cargo_nivel", description="Adiciona um cargo a um nível de permissão existente.")
@app_commands.describe(
    nivel="Número do nível de permissão existente.", # Corrigido para INT
    cargo="Cargo que deseja adicionar a esse nível."
)
async def add_cargo_nivel(interaction: discord.Interaction, nivel: int, cargo: discord.Role):
    # Verifica se o comando foi usado em um servidor
    if not interaction.guild:
        return await interaction.response.send_message("❌ Este comando só pode ser usado em servidores.", ephemeral=True)

    guild_id = str(interaction.guild.id)
    cargo_nome = cargo.name # Pegar o nome do cargo

    try:
        # Abre conexão com o banco de dados
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        # Verifica se o nível existe na tabela 'niveis'
        c.execute("SELECT 1 FROM niveis WHERE guild_id = ? AND nivel = ?", (guild_id, nivel))
        if not c.fetchone():
            conn.close()
            return await interaction.response.send_message(
                f"❌ O nível `{nivel}` não existe. Use `/criar_nivel` para criar um novo nível antes.",
                ephemeral=True
            )

        # Verifica se o cargo já está associado a esse nível (usando cargo_nome)
        c.execute("SELECT 1 FROM cargos_permissao WHERE guild_id = ? AND nivel = ? AND cargo_nome = ?", (guild_id, nivel, cargo_nome))
        if c.fetchone():
            conn.close()
            return await interaction.response.send_message(
                f"⚠️ O cargo {cargo.mention} **já está associado** ao nível `{nivel}`.",
                ephemeral=True
            )

        # Adiciona o cargo ao nível (usando cargo_nome)
        c.execute("INSERT INTO cargos_permissao (guild_id, nivel, cargo_nome) VALUES (?, ?, ?)", (guild_id, nivel, cargo_nome))
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
    nivel="Número do nível do qual o cargo será removido.", # Corrigido para INT
    cargo="Cargo que deseja remover desse nível."
)
async def remover_cargo_nivel(interaction: discord.Interaction, nivel: int, cargo: discord.Role):
    # Verifica se o comando foi usado em um servidor
    if not interaction.guild:
        return await interaction.response.send_message("❌ Este comando só pode ser usado em servidores.", ephemeral=True)

    guild_id = str(interaction.guild.id)
    cargo_nome = cargo.name # Pegar o nome do cargo

    try:
        # Abre conexão com o banco de dados
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        # Verifica se o nível existe
        c.execute("SELECT 1 FROM niveis WHERE guild_id = ? AND nivel = ?", (guild_id, nivel))
        if not c.fetchone():
            conn.close()
            return await interaction.response.send_message(
                f"❌ O nível `{nivel}` não existe. Use `/criar_nivel` para criar um novo nível.",
                ephemeral=True
            )

        # Verifica se o cargo está associado a esse nível (usando cargo_nome)
        c.execute("SELECT 1 FROM cargos_permissao WHERE guild_id = ? AND nivel = ? AND cargo_nome = ?", (guild_id, nivel, cargo_nome))
        if not c.fetchone():
            conn.close()
            return await interaction.response.send_message(
                f"⚠️ O cargo {cargo.mention} **não está associado** ao nível `{nivel}`.",
                ephemeral=True
            )

        # Remove o cargo do nível (usando cargo_nome)
        c.execute("DELETE FROM cargos_permissao WHERE guild_id = ? AND nivel = ? AND cargo_nome = ?", (guild_id, nivel, cargo_nome))
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
async def remover_cadastro_cmd(interaction: discord.Interaction, membro: discord.Member): # Renomeado para evitar conflito com a função utility 'remover_cadastro'
    # Verifica se o comando foi usado em um servidor
    if not interaction.guild:
        return await interaction.response.send_message("❌ Este comando só pode ser usado em servidores.", ephemeral=True)

    guild_id = str(interaction.guild.id)
    user_id = str(membro.id)

    try:
        # --- 🔒 Verifica permissão dinâmica (baseada nos níveis configurados) ---
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Obtém os nomes dos cargos de permissão
        c.execute("SELECT DISTINCT cargo_nome FROM cargos_permissao WHERE guild_id = ?", (guild_id,))
        cargos_autorizados_nomes = [cargo_nome for (cargo_nome,) in c.fetchall()]
        
        cargos_membro = [role.name for role in interaction.user.roles]
        
        # Verifica se o autor tem algum dos cargos de permissão
        if not any(cargo_nome in cargos_membro for cargo_nome in cargos_autorizados_nomes):
            conn.close()
            return await interaction.response.send_message(
                "🚫 Você **não tem permissão** para remover cadastros. É necessário ter um cargo associado a um nível.",
                ephemeral=True
            )

        # --- 🔍 Verifica se o membro está cadastrado (usando 'usuario_id') ---
        c.execute("SELECT * FROM recrutamentos WHERE guild_id = ? AND usuario_id = ?", (guild_id, user_id))
        registro = c.fetchone()

        if not registro:
            conn.close()
            return await interaction.response.send_message(
                f"⚠️ O membro {membro.mention} **não está cadastrado** no sistema.",
                ephemeral=True
            )

        # --- 🗑️ Remove o registro ---
        # Usa a função utilitária para manter o código limpo
        remover_cadastro(interaction.guild.id, membro.id)
        
        # Busca os nomes dos cargos de setagem e canal de log
        c.execute("SELECT cargo_padrao, cargo_crianca, canal_log_id FROM config WHERE guild_id = ?", (guild_id,))
        resultado = c.fetchone()
        conn.close()
        
        cargo_padrao_nome = resultado[0] if resultado else None
        cargo_crianca_nome = resultado[1] if resultado else None
        canal_logs_id = resultado[2] if resultado else None

        # Cria o embed de confirmação
        embed = discord.Embed(
            title="🗑️ Cadastro removido",
            description=f"O membro {membro.mention} foi **removido do cadastro** com sucesso!",
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Servidor: {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)

        await interaction.response.send_message(embed=embed, ephemeral=True)

        # --- 🎭 Remove o cargo do membro (se configurado) ---
        cargos_a_remover = []
        
        if cargo_padrao_nome:
            cargo_padrao = discord.utils.get(interaction.guild.roles, name=cargo_padrao_nome)
            if cargo_padrao and cargo_padrao in membro.roles:
                cargos_a_remover.append(cargo_padrao)
                
        if cargo_crianca_nome:
            cargo_crianca = discord.utils.get(interaction.guild.roles, name=cargo_crianca_nome)
            if cargo_crianca and cargo_crianca in membro.roles:
                cargos_a_remover.append(cargo_crianca)

        if cargos_a_remover:
            try:
                await membro.remove_roles(*cargos_a_remover, reason="Remoção de cadastro de recrutamento")
            except discord.Forbidden:
                await interaction.followup.send(
                    f"⚠️ Não consegui remover o(s) cargo(s) de setagem de {membro.mention}. Verifique minhas permissões.",
                    ephemeral=True
                )

        # --- 🪵 Loga a ação (se canal de logs configurado) ---
        if canal_logs_id:
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

    guild_id = str(interaction.guild.id)

    try:
        # --- 🔒 Verificação de permissão dinâmica ---
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Obtém os nomes dos cargos de permissão
        c.execute("SELECT DISTINCT cargo_nome FROM cargos_permissao WHERE guild_id = ?", (guild_id,))
        cargos_autorizados_nomes = [cargo_nome for (cargo_nome,) in c.fetchall()]
        
        cargos_membro = [role.name for role in interaction.user.roles]
        
        if not any(cargo_nome in cargos_membro for cargo_nome in cargos_autorizados_nomes):
            conn.close()
            return await interaction.response.send_message(
                "🚫 Você **não tem permissão** para listar cadastros. É necessário ter um cargo associado a um nível.",
                ephemeral=True
            )

        # --- 📋 Obtém os cadastros (Ajuste: usando apenas as colunas existentes) ---
        recrutador_id_str = str(recrutador.id) if recrutador else None
        
        if recrutador:
            c.execute("""
                SELECT usuario_id, recrutador_id, data 
                FROM recrutamentos 
                WHERE guild_id = ? AND recrutador_id = ?
                ORDER BY data DESC
            """, (guild_id, recrutador_id_str))
        else:
            c.execute("""
                SELECT usuario_id, recrutador_id, data 
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
            titulo = "📋 Cadastros de Recrutamento"
            if recrutador:
                titulo += f" de {recrutador.display_name}"

            embed = discord.Embed(
                title=titulo,
                description=f"Página {pagina_idx + 1}/{total_paginas}",
                color=discord.Color.blurple()
            )

            for usuario_id_str, recrutador_id_str, data in paginas[pagina_idx]:
                usuario_id = int(usuario_id_str)
                recrutador_id = int(recrutador_id_str)
                
                membro = interaction.guild.get_member(usuario_id)
                recrutador_info = interaction.guild.get_member(recrutador_id)
                
                nome_exibido = membro.display_name if membro else f"ID {usuario_id} (Saiu)"
                recrutador_nome = recrutador_info.display_name if recrutador_info else f"ID {recrutador_id} (Saiu)"
                
                try:
                    data_formatada = datetime.fromisoformat(data).strftime('%d/%m/%Y %H:%M:%S')
                except ValueError:
                    data_formatada = data

                embed.add_field(
                    name=f"👤 {nome_exibido}",
                    value=f"🎯 **Recrutador:** {recrutador_nome}\n"
                          f"📅 **Data:** {data_formatada}",
                    inline=False
                )

            embed.set_footer(text=f"Total de registros: {len(registros)}")
            return embed

        # --- 🔘 View com botões de navegação ---
        class PaginacaoView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=180)
                self.pagina_atual = 0

            async def on_timeout(self):
                if self.message:
                    for child in self.children:
                        child.disabled = True
                    await self.message.edit(view=self)

            async def actualizar(self, interaction_update: discord.Interaction):
                embed = gerar_embed(self.pagina_atual)
                await interaction_update.response.edit_message(embed=embed, view=self)

            @discord.ui.button(label="⏮️", style=discord.ButtonStyle.gray, row=1)
            async def inicio(self, interaction_button: discord.Interaction, _):
                self.pagina_atual = 0
                await self.actualizar(interaction_button)

            @discord.ui.button(label="⬅️", style=discord.ButtonStyle.blurple, row=1)
            async def anterior(self, interaction_button: discord.Interaction, _):
                if self.pagina_atual > 0:
                    self.pagina_atual -= 1
                await self.actualizar(interaction_button)

            @discord.ui.button(label="➡️", style=discord.ButtonStyle.blurple, row=1)
            async def proxima(self, interaction_button: discord.Interaction, _):
                if self.pagina_atual < total_paginas - 1:
                    self.pagina_atual += 1
                await self.actualizar(interaction_button)

            @discord.ui.button(label="⏭️", style=discord.ButtonStyle.gray, row=1)
            async def fim(self, interaction_button: discord.Interaction, _):
                self.pagina_atual = total_paginas - 1
                await self.actualizar(interaction_button)


        view = PaginacaoView()
        await interaction.response.send_message(embed=gerar_embed(0), view=view, ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(f"❌ Erro ao listar cadastros: `{e}`", ephemeral=True)


# Listar todos os níveis e cargos
@bot.tree.command(name="listar_niveis", description="Mostra todos os níveis e cargos configurados no servidor.")
async def listar_niveis(interaction: discord.Interaction):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Obter nomes dos níveis
    c.execute("SELECT nivel, nome FROM niveis WHERE guild_id=? ORDER BY nivel", (str(interaction.guild.id),))
    niveis_map = {nivel: nome for nivel, nome in c.fetchall()}
    
    # 2. Obter cargos por nível
    c.execute("SELECT nivel, cargo_nome FROM cargos_permissao WHERE guild_id=? ORDER BY nivel, cargo_nome", (str(interaction.guild.id),))
    resultados = c.fetchall()
    conn.close()
    
    if not niveis_map and not resultados:
        await interaction.response.send_message("⚠️ Nenhum nível configurado.", ephemeral=True)
        return
        
    msg = ""
    niveis_agrupados = {}
    
    # Agrupar cargos por nível
    for nivel, cargo in resultados:
        if nivel not in niveis_agrupados:
            niveis_agrupados[nivel] = []
        niveis_agrupados[nivel].append(f"`{cargo}`")
        
    # Construir a mensagem
    for nivel, nome in sorted(niveis_map.items()):
        cargos = ", ".join(niveis_agrupados.get(nivel, ["*Nenhum cargo*"]))
        msg += f"**Nível {nivel} - {nome}**\n   → Cargos: {cargos}\n"
        
    embed = discord.Embed(
        title="📑 Níveis de Permissão Dinâmica",
        description=msg,
        color=discord.Color.blue()
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="configurar_tempo_expiracao",
    description="Define o tempo (em minutos) até que uma solicitação de set expire automaticamente."
)
@app_commands.describe(minutos="Tempo em minutos (1-120)")
async def configurar_tempo_expiracao(interaction: discord.Interaction, minutos: int):
    # Checando permissão em nível 0 (mais alto)
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
    def __init__(self, nivel_usuario: int, acoes: list):
        super().__init__(timeout=None)
        self.nivel_usuario = nivel_usuario
        
        # Adiciona botões dinamicamente com base nas ações do nível
        if "configuracao" in acoes:
            self.add_item(discord.ui.Button(label="⚙️ Configurações",
                                  style=discord.ButtonStyle.primary, custom_id="config")) # Exemplo de custom_id
        if "relatorios" in acoes:
            self.add_item(discord.ui.Button(
                label="📊 Relatórios", style=discord.ButtonStyle.success, custom_id="relatorio")) # Exemplo de custom_id
        if "visual" in acoes:
            self.add_item(discord.ui.Button(
                label="🎨 Visual", style=discord.ButtonStyle.secondary, custom_id="visual")) # Exemplo de custom_id

    # Botão para atualizar o painel
    @discord.ui.button(label="🧭 Atualizar painel", style=discord.ButtonStyle.gray, row=1)
    async def atualizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # CORREÇÃO APLICADA AQUI: Chamar a função _exibir_painel_logica diretamente
        await _exibir_painel_logica(interaction)

    async def interaction_check(self, interaction: discord.Interaction):
        # Você pode adicionar verificações aqui se quiser restringir quem pode interagir com o painel
        return True 


# Função auxiliar que contém a lógica de exibição do painel
async def _exibir_painel_logica(interaction: discord.Interaction):
    user = interaction.user
    guild_id = interaction.guild.id

    # Detecta o nível mais alto do usuário
    nivel_usuario = None
    
    todos_niveis = niveis_disponiveis(guild_id) # Esta função deve retornar os níveis numéricos
    
    for nivel in sorted(todos_niveis, reverse=True): # Começa do nível mais alto
        # Checa se o usuário tem permissão para este nível
        if checar_permissao_multiplos_niveis(user, nivel):
            nivel_usuario = nivel
            break

    if nivel_usuario is None:
        await interaction.response.send_message(
            "🔒 Você não possui nenhum nível de permissão configurado ou não tem acesso.",
            ephemeral=True
        )
        return

    # Obtém as ações configuradas para o nível do usuário
    acoes = obter_acoes_nivel(guild_id, nivel_usuario)
    
    # Cria o embed do painel
    embed = discord.Embed(
        title=f"🧭 Painel de Controle (Nível {nivel_usuario})",
        description="Selecione uma das opções abaixo para ver seus comandos disponíveis:",
        color=discord.Color.blue()
    )

    if "configuracao" in acoes:
        embed.add_field(
            name="⚙️ Configurações",
            value="`/configuração`, `/criar_nivel`, `/add_cargo_nivel`, `/remover_cargo_nivel`, `/configurar_tempo_expiracao`",
            inline=False
        )
    if "relatorios" in acoes:
        embed.add_field(
            name="📊 Relatórios",
            value="`/ranking_de_rec`, `/listar_cadastros`, `/remover_cadastro`",
            inline=False
        )
    if "visual" in acoes:
        embed.add_field(
            name="🎨 Visual",
            value="`/enviar_botao_recrutamento`, `/setar_mensagem_botao`",
            inline=False
        )
    if "atribuicao_acao" in acoes: # Novo campo se você quiser ter uma ação específica para atribuir_acao
         embed.add_field(
            name="🛠️ Atribuição de Ações",
            value="`/atribuir_acao`",
            inline=False
        )

    # Se não houver ações configuradas para este nível
    if not acoes:
        embed.add_field(name="Sem Ações", value="Nenhuma ação foi configurada para o seu nível.", inline=False)

    # Envia o painel com a View contendo os botões
    # Se a interação já foi respondida (ex: por um Select antes), usa followu.send
    # Caso contrário, usa response.send_message
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, view=PainelView(nivel_usuario, acoes), ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, view=PainelView(nivel_usuario, acoes), ephemeral=True)


# Comando /painel
@bot.tree.command(
    name="painel",
    description="Mostra o painel de controle conforme seu nível de permissão."
)
async def comando_painel(interaction: discord.Interaction):
    # O comando de barra agora chama a função auxiliar _exibir_painel_logica
    await _exibir_painel_logica(interaction)


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

