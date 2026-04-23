from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    EmailField,
    IntegerField,
    PasswordField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, Optional


class RegisterForm(FlaskForm):
    name = StringField('Nome', validators=[DataRequired(), Length(min=2, max=120)])
    email = EmailField('E-mail', validators=[DataRequired(), Email(), Length(max=160)])
    whatsapp = StringField('WhatsApp', validators=[DataRequired(), Length(min=10, max=20)])
    password = PasswordField('Senha', validators=[DataRequired(), Length(min=6, max=128)])
    confirm_password = PasswordField(
        'Confirmar senha',
        validators=[DataRequired(), EqualTo('password', message='As senhas não coincidem.')],
    )
    submit = SubmitField('Criar conta')


class LoginForm(FlaskForm):
    email = EmailField('E-mail', validators=[DataRequired(), Email(), Length(max=160)])
    password = PasswordField('Senha', validators=[DataRequired(), Length(min=6, max=128)])
    submit = SubmitField('Entrar')


class GoalForm(FlaskForm):
    target_income_month = StringField('Meta mensal', validators=[DataRequired(), Length(max=40)])
    use_commission = BooleanField('Trabalho com comissão')
    commission_percent = StringField('Comissão média (%)', validators=[Optional(), Length(max=20)])
    working_days_month = IntegerField('Dias trabalhados no mês', validators=[DataRequired(), NumberRange(min=1, max=31)])
    submit = SubmitField('Salvar meta')


class DailyResultForm(FlaskForm):
    date = DateField('Data', validators=[DataRequired()])
    sales_value = StringField('Valor vendido no dia', validators=[DataRequired(), Length(max=40)])
    attendance_count = IntegerField('Atendimentos', validators=[DataRequired(), NumberRange(min=0)])
    closed_deals = IntegerField('Fechamentos', validators=[DataRequired(), NumberRange(min=0)])
    notes = TextAreaField('Observações', validators=[Optional(), Length(max=1000)])
    submit = SubmitField('Salvar resultado')


class ChecklistForm(FlaskForm):
    date = DateField('Data', validators=[DataRequired()])
    leads_answered = BooleanField('Respondi os leads')
    follow_up_done = BooleanField('Fiz follow-up')
    proposals_sent = BooleanField('Enviei propostas')
    post_sale_done = BooleanField('Fiz pós-venda')
    goal_reviewed = BooleanField('Revisei a meta do dia')
    submit = SubmitField('Salvar checklist')


class AdminAccessForm(FlaskForm):
    paid_days = IntegerField('Liberar por quantos dias?', validators=[Optional(), NumberRange(min=1, max=3650)])
    reason = StringField('Motivo', validators=[Optional(), Length(max=255)])
    submit = SubmitField('Salvar')