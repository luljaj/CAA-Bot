from discord.ext import commands
from discord import app_commands, Interaction, Object
import os
import discord

from config import get_employee_role, get_intern_role

GUILD_ID = int(os.getenv("GUILDID"))


class Employee(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = bot.supabase
    @app_commands.command(
        name="employee",
        description="Upgrade an intern to employee."
    )
    @app_commands.default_permissions(manage_events=True)  
    @app_commands.guilds(Object(id=GUILD_ID)) 


    async def employee(self, interaction: Interaction, user: discord.User):
        self.user = user

        employee = get_employee_role(interaction.guild)
        intern = get_intern_role(interaction.guild)
        if employee is None or intern is None:
            await interaction.response.send_message(
                "Employee or Intern role is not configured.",
                ephemeral=True
            )
            return
        
        await self.user.add_roles(employee, reason = f'Employee promoted by <@{interaction.user.name}>')
        await self.user.remove_roles(intern, reason = f'Employee promoted by <@{interaction.user.name}>')


        await interaction.response.send_message(f'{user.mention}\'s has been promoted to Employee.', ephemeral=True)
        
async def setup(bot):
    await bot.add_cog(Employee(bot))
