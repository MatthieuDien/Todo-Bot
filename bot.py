"""
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.

    All rights reserverd :
    + Matthieu Dien (co-designer, developper)
    + Paul Dorbec (bugs introducer)
    + Gaétan Richard (co-designer)

To manage the work of the bot over several channels themselves over several servers,
we use two main data structures : `Server` and `ExerciseSession`.
The architecture follows (more or less) a MVC pattern :
- `Server` is a kind of controler between the view (the bot commands) and the model
  (the `ExerciseSession` instances of a guild)
- `ExerciseSession` is a model which deals with all the logic of user registering,
  tasks completions, etc
- the commands (function decorated with @bot.command) are used to input/outpout
  informations by the users

Moreover, there is a global table `servers` identifying Discord guilds with
`Server` instances. That is why the pattern
```
    serv = servers[ctx.guild]
    session = serv.sessions[ctx.channel]
```
can be found several times along the code to identify the channel (and so
the `ExerciseSession`) from where comes the command.
See [discord.py manual](https://discordpy.readthedocs.io/en/latest/index.html)
for details.

### TODO
- add documentation
- add tests
- send some troll to Paul about Java
"""

from discord.ext import commands
from functools import reduce, wraps
from collections import defaultdict
from math import ceil
from datetime import datetime


class ExerciseSession:
    def __init__(self, channel):
        self.channel = channel
        self.students = set()
        self.exos = list()
        self.exos_name = list()

    def str_exos_done(self, details=False):
        msg = ""
        for i, name in enumerate(self.exos_name):
            if not details:
                percent = int(ceil(len(self.exos[i]) / len(self.students) * 100))
                msg += f"**{i}.** {name} : {percent}%\n"
            else:
                msg += f"**{i}.** {name} : "
                msg += ", ".join([f"{s.name}>" for s in self.exos[i]])
                msg += "\n"
        return msg

    def str_exos(self):
        msg = ""
        for i, name in enumerate(self.exos_name):
            msg += f"**{i}.** {name}\n"
        return msg

    def done(self, student, exo_id: int):
        self.exos[exo_id].add(student)

    def undone(self, student, exo_id: int):
        self.exos[exo_id].remove(student)

    def register(self, student):
        self.students.add(student)

    def is_registered(self, student):
        return student in self.students

    def not_finish(self, exo_id: int):
        return self.students - self.exos[exo_id]

    def add_exo(self, name):
        self.exos_name.append(name)
        self.exos.append(set())

    def remove_exo(self, i):
        del self.exos[i]
        del self.exos_name[i]

    def personal_progress(self, student):
        exos_done = set(
            filter(lambda i: student in self.exos[i], range(len(self.exos)))
        )
        msg = ""
        for i, name in enumerate(self.exos_name):
            msg += ":x:" if i not in exos_done else ":white_check_mark:"
            msg += f" **{i}.** {name}\n"
        return msg

    def __str__(self):
        return str(self.channel)


class Server:
    def __init__(self, guild):
        self.guild = guild
        self.students_sessions = defaultdict(set)  # student : ExerciseSession
        self.sessions = dict()  # channel : ExerciseSession

    def start_session(self, chan):
        session = ExerciseSession(chan)
        self.sessions[chan] = session
        return session

    def register(self, student, chan):
        session = self.sessions[chan]
        self.students_sessions[student].add(session)
        session.register(student)

    def end_session(self, chan):
        session = self.sessions[chan]
        for student in self.sessions[chan].students:
            self.students_sessions[student].remove(session)
        del self.sessions[chan]


servers = dict()

bot = commands.Bot(command_prefix="$")


def remove_invoke(f):
    @wraps(f)
    async def wrapper(ctx, *args, **kwargs):
        res = await f(ctx, *args, **kwargs)
        await ctx.message.delete()
        return res

    return wrapper


class NotRegistered(commands.CheckFailure):
    pass


def is_registered():
    def predicate(ctx):
        serv = servers[ctx.guild]
        session = serv.sessions[ctx.channel]
        if session.is_registered(ctx.author):
            return True
        else:
            raise NotRegistered()

    return commands.check(predicate)


class SessionNotStarted(commands.CheckFailure):
    pass


def is_session_started():
    def predicate(ctx):
        serv = servers[ctx.guild]
        if ctx.channel in serv.sessions:
            return True
        else:
            raise SessionNotStarted()

    return commands.check(predicate)


@bot.event
async def on_ready():
    print("We have logged in as {0.user}".format(bot))
    for guild in bot.guilds:
        servers[guild] = Server(guild)


@bot.command()
@remove_invoke
@commands.has_role("Professeur")
async def start_session(ctx, *exercises):
    serv = servers[ctx.guild]
    if ctx.channel in serv.sessions:
        await ctx.send("Une session est déjà commencée avec les exercices :\n")
        await ctx.send(serv.sessions[ctx.channel].str_exos())
    else:
        session = serv.start_session(ctx.channel)
        for exo in exercises:
            session.add_exo(exo)
        msg = "La session d'exercices est commencée. La liste des exercices est :\n"
        msg += serv.sessions[ctx.channel].str_exos()
        msg += "Enregistrez vous avec la commande `$register`"
        await ctx.send(msg)


@bot.command()
@is_session_started()
@commands.has_role("Professeur")
async def end_session(ctx):
    serv = servers[ctx.guild]
    serv.end_session(ctx.channel)
    await ctx.send("J'ai fini mon job. Bye !")


@bot.command()
@remove_invoke
@is_session_started()
@commands.has_role("Professeur")
async def add_exo(ctx, *names):
    serv = servers[ctx.guild]
    session = serv.sessions[ctx.channel]
    for name in names:
        session.add_exo(name)
    msg = "La liste des exercices est :\n"
    msg += serv.sessions[ctx.channel].str_exos()
    await ctx.send(msg)


@bot.command()
@remove_invoke
@is_session_started()
@commands.has_role("Professeur")
async def remove_exo(ctx, *ids):
    serv = servers[ctx.guild]
    session = serv.sessions[ctx.channel]
    for i in ids:
        session.remove_exo(int(i))
    msg = "La liste des exercices est :\n"
    msg += serv.sessions[ctx.channel].str_exos()
    await ctx.send(msg)


@bot.command()
@remove_invoke
@is_session_started()
@commands.has_role("Professeur")
async def who_registered(ctx):
    """affiche en MP la liste des etudiants qui se sont enregistres dans la session"""
    serv = servers[ctx.guild]
    session = serv.sessions[ctx.channel]
    if ctx.author.dm_channel is None:
        await ctx.author.create_dm()
    await ctx.author.dm_channel.send(
        f"Les utilisateurs enregistrés sur <#{ctx.channel.id}> sont: \n"
    )
    students = session.students
    for student in students:
        await ctx.author.dm_channel.send(f"<@{student.id}>")


@bot.command()
@remove_invoke
@is_session_started()
async def register(ctx):
    serv = servers[ctx.guild]
    session = serv.sessions[ctx.channel]
    serv.students_sessions[ctx.author].add(session)
    session.register(ctx.author)


@bot.command()
@is_registered()
@remove_invoke
@is_session_started()
async def done(ctx, *exos):
    serv = servers[ctx.guild]
    session = serv.sessions[ctx.channel]
    for exo in exos:
        session.done(ctx.author, int(exo))


@bot.command()
@is_registered()
@remove_invoke
@is_session_started()
async def undone(ctx, *exos):
    serv = servers[ctx.guild]
    session = serv.sessions[ctx.channel]
    for exo in exos:
        session.undone(ctx.author, int(exo))


@bot.command()
@remove_invoke
@is_session_started()
async def progress(ctx, *args):
    serv = servers[ctx.guild]
    session = serv.sessions[ctx.channel]
    is_prof = "Professeur" in map(lambda x: x.name, ctx.author.roles)
    details = True if is_prof and ("with_details" in args) else False
    for_all = True if is_prof and ("for_all" in args) else False
    if not for_all:
        if ctx.author.dm_channel is None:
            await ctx.author.create_dm()
        await ctx.author.dm_channel.send(session.str_exos_done(details))
    else:
        await ctx.send(session.str_exos_done(details))


@bot.command()
@remove_invoke
@is_registered()
@is_session_started()
async def my_progress(ctx):
    serv = servers[ctx.guild]
    session = serv.sessions[ctx.channel]
    if ctx.author.dm_channel is None:
        await ctx.author.create_dm()
    await ctx.author.dm_channel.send(session.personal_progress(ctx.author))
    # await ctx.send(session.personal_progress(ctx.author))


@bot.command()
@remove_invoke
async def my_registrations(ctx):
    serv = servers[ctx.guild]
    if ctx.author.dm_channel is None:
        await ctx.author.create_dm()
    await ctx.author.dm_channel.send(
        f"Vous êtes enregistré par <@{bot.id}> sur les chans : "
        + ", ".join(map(lambda s: f"<#{str(s)}>", serv.students_sessions[ctx.author]))
    )


@bot.command()
@commands.is_owner()
async def dump_datas(ctx):
    now = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    with open(f"dump-{now}", "w") as fd:
        print(servers)
        for guild in servers:
            fd.write(f"Server : {(guild.name, guild.id)}\n")
            for chan, session in servers[guild].sessions.items():
                print(session)
                fd.write(f"  {(str(session), chan.id)} :\n")
                fd.write("    students : ")
                fd.write(", ".join([str((s.name, s.id)) for s in session.students]))
                fd.write("\n")
                for i in range(len(session.exos)):
                    fd.write(f"    '{session.exos_name[i]}' : ")
                    fd.write(", ".join([str((s.name, s.id)) for s in session.exos[i]]))
                    fd.write("\n")


# TODO
# @bot.command()
# @commands.is_owner()
# async def load_datas(ctx, date):
#     with open(f"dump-{date}", "r") as fd:
#         server = None
#         chan = None
#         for line in fd:
#             if line

#         for guild in servers:
#             fd.write(f"Server : {guild}\n")
#             for chan, session in servers[guild].sessions.items():
#                 print(session)
#                 fd.write(f"  {str(session)} :\n")
#                 for i in range(len(session.exos)):
#                     fd.write("    students : ")
#                     fd.write(", ".join(map(str, session.students)))
#                     fd.write(f"\n    {session.exos_name[i]} : ")
#                     fd.write(", ".join(map(str, session.exos[i])))
#                     fd.write("\n")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.MissingRole):
        await ctx.send(
            f"Seul les {error.missing_role} peuvent utiliser cette commande."
        )
    elif isinstance(error, commands.errors.CommandNotFound):
        await ctx.send(
            f"Je ne connais pas cette commande. Essayes `$help` si tu as besoin d'aide."
        )
    elif isinstance(error, NotRegistered):
        await ctx.send("Désolé, mais tu ne t'es pas enregistré. Tapes `$register` !")
    elif isinstance(error, SessionNotStarted):
        await ctx.send(
            "Désolé, la session n'est pas démarrée. Demande à un Professeur de le faire."
        )
    else:
        return await commands.Bot.on_command_error(bot, ctx, error)


bot.remove_command("help")


@bot.command()
@remove_invoke
async def help(ctx):
    msg = f"Les commandes de {bot.user} sont :\n"
    msg += "  `$register` : Vous enregistre dans la session d'exercices courante sur le salon\n"
    msg += "  `$done | $done n1 n2 n3 ...` : Signifie que vous avez fini les exercices numéro `n1 n2 n3` (sans argument, liste les exercices)\n"
    msg += "  `$undone n1 n2 n3 ...` : Pour corriger `$done n1 n2 n3 ...`\n"
    msg += "  `$my_progress` : Montre les exercices que vous avez faits\n"
    msg += "  `$my_registrations` : Montre les sessions d'exercices auxquelles vous êtes inscrit.e.s\n"
    if "Professeur" in map(lambda x: x.name, ctx.author.roles):
        msg += "  `$start_session exo_1 ... exo_n` : démarre une session d'exercices avec les noms d'exercices `exo_1` ... `exo_n`\n"
        msg += '  `$add_exo "exo 1" exo2 ...`  : ajoute des exercices à la session **en cours**\n'
        msg += "  `$remove_exo 0 1 2 3 ...`  : supprime les exercices mentionnés (par leur numéro)\n"
        msg += "  `$end_session` : termine la session\n"
        msg += "  `$who_registered` : donne la liste des étudiants enregistrés\n"
        msg += "  `$progress [with_details] [for_all]` : affiche la progression globale avec l'option d'avoir les noms d'étudiants (`with_details`)\n"
        msg += "                                         et de l'afficher dans le salon (`for_all`) ou en privé (par défaut)\n"
    else:
        msg += "  `$progress` : affiche la progression globale\n"
    if ctx.author.dm_channel is None:
        await ctx.author.create_dm()
    await ctx.author.dm_channel.send(msg)



import private

bot.run(private.token)
