from datetime import date, datetime, timedelta
import os
import random
import requests
from flask import Flask, flash, redirect, render_template, request, session, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import sqlalchemy

app = Flask(__name__)
# Configuración segura de clave secreta y credenciales de correo
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'clave_secreta_super_segura')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)
app.config['SESSION_PERMANENT'] = True

# Ajuste seguro de la ruta de la base de datos
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'prestamos.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ==========================================
# CONFIGURACIÓN DE CORREO (API HTTPS DE BREVO)
# ==========================================
BREVO_API_KEY = os.environ.get('BREVO_API_KEY')
BREVO_SENDER_EMAIL = os.environ.get('BREVO_SENDER_EMAIL', os.environ.get('MAIL_USERNAME'))
BREVO_SENDER_NAME = 'Fenix Credit'

db = SQLAlchemy(app)


@app.context_processor
def inject_usuario_actual():
    usuario_actual = None
    if 'user_id' in session:
        usuario_actual = db.session.get(Usuario, session['user_id'])
    return dict(usuario_actual=usuario_actual)


def enviar_correo(destinatario, asunto, cuerpo_texto):
    """Envía un correo transaccional usando la API HTTPS de Brevo.
    Devuelve True si Brevo confirmó el envío, False en caso contrario."""
    if not BREVO_API_KEY:
        app.logger.warning('BREVO_API_KEY no está configurada; no se pudo enviar el correo.')
        return False
    try:
        resp = requests.post(
            'https://api.brevo.com/v3/smtp/email',
            headers={
                'api-key': BREVO_API_KEY,
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            json={
                'sender': {'name': BREVO_SENDER_NAME, 'email': BREVO_SENDER_EMAIL},
                'to': [{'email': destinatario}],
                'subject': asunto,
                'textContent': cuerpo_texto,
            },
            timeout=10,
        )
        if resp.status_code in (200, 201):
            return True
        app.logger.warning(f'Brevo respondió {resp.status_code}: {resp.text}')
        return False
    except requests.RequestException as e:
        app.logger.warning(f'Error de red al enviar correo con Brevo: {e}')
        return False


# ==========================================
# MODELOS DE BASE DE DATOS
# ==========================================

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    nombre = db.Column(db.String(120))
    foto = db.Column(db.String(255))


class Ruta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    descripcion = db.Column(db.String(250), nullable=True)
    color = db.Column(db.String(30), default='Azul')
    cobrador = db.Column(db.String(100), nullable=True)
    estado = db.Column(db.String(20), default='Activa')
    
    clientes = db.relationship('Cliente', backref='ruta', lazy=True)


class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(20), nullable=False)
    cedula = db.Column(db.String(30), nullable=True)
    direccion = db.Column(db.String(255), nullable=True)
    ocupacion = db.Column(db.String(120), nullable=True)
    fecha_nacimiento = db.Column(db.String(20), nullable=True)
    
    ruta_id = db.Column(db.Integer, db.ForeignKey('ruta.id'), nullable=True)
    orden_ruta = db.Column(db.Integer, default=0)
    
    prestamos = db.relationship('Prestamo', backref='cliente', lazy=True, cascade="all, delete-orphan")


class Prestamo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    capital_inicial = db.Column(db.Float, nullable=False)
    capital_actual = db.Column(db.Float, nullable=False, default=0.0)
    tasa_interes = db.Column(db.Float, nullable=False)
    cuotas_totales = db.Column(db.Integer, nullable=True)
    modalidad = db.Column(db.String(50), default='MENSUAL')
    tipo_amortizacion = db.Column(db.String(50), default='CAPITAL AL FINAL')
    porcentaje_mora = db.Column(db.Float, default=0.0)
    porcentaje_comision = db.Column(db.Float, default=0.0)
    
    codeudor_nombre = db.Column(db.String(100), nullable=True)
    codeudor_identificacion = db.Column(db.String(50), nullable=True)
    codeudor_telefono = db.Column(db.String(30), nullable=True)
    codeudor_direccion = db.Column(db.String(200), nullable=True)

    proximo_pago = db.Column(db.String(20), nullable=False)
    estado = db.Column(db.String(20), default='Activo')
    
    cuotas = db.relationship('CuotaPrestamo', backref='prestamo', lazy=True, cascade="all, delete-orphan", order_by="CuotaPrestamo.numero_cuota")
    pagos = db.relationship('Pago', backref='prestamo', lazy=True, cascade="all, delete-orphan")


class CuotaPrestamo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prestamo_id = db.Column(db.Integer, db.ForeignKey('prestamo.id'), nullable=False)
    numero_cuota = db.Column(db.Integer, nullable=False)
    fecha_vencimiento = db.Column(db.String(20), nullable=False)
    valor_cuota = db.Column(db.Float, nullable=False)
    interes_esperado = db.Column(db.Float, nullable=False)
    capital_esperado = db.Column(db.Float, nullable=False)
    estado = db.Column(db.String(20), default='Pendiente')


class Pago(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prestamo_id = db.Column(db.Integer, db.ForeignKey('prestamo.id'), nullable=False)
    concepto = db.Column(db.String(100), nullable=False)
    fecha = db.Column(db.String(20), nullable=False)
    fecha_vencimiento = db.Column(db.String(20), nullable=False)
    total_pago = db.Column(db.Float, nullable=False)
    capital = db.Column(db.Float, default=0.0)
    interes = db.Column(db.Float, default=0.0)
    mora = db.Column(db.Float, default=0.0)


class SolicitudPrestamo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    monto_solicitado = db.Column(db.Float, nullable=False)
    cuotas = db.Column(db.Integer, nullable=True)
    motivo = db.Column(db.String(250), nullable=True)
    estado = db.Column(db.String(30), default='Pendiente')
    fecha_solicitud = db.Column(db.String(20), default=lambda: date.today().strftime('%Y-%m-%d'))


# ==========================================
# INICIALIZACIÓN DE LA BASE DE DATOS
# ==========================================

with app.app_context():
    db.create_all()

    with db.engine.connect() as conn:
        columnas_existentes = {fila[1] for fila in conn.execute(sqlalchemy.text("PRAGMA table_info(cliente)"))}
        columnas_nuevas = {
            'cedula': 'VARCHAR(30)',
            'direccion': 'VARCHAR(255)',
            'ocupacion': 'VARCHAR(120)',
            'fecha_nacimiento': 'VARCHAR(20)',
        }
        for nombre_columna, tipo_sql in columnas_nuevas.items():
            if nombre_columna not in columnas_existentes:
                conn.execute(sqlalchemy.text(f'ALTER TABLE cliente ADD COLUMN {nombre_columna} {tipo_sql}'))
                conn.commit()

        columnas_usuario_existentes = {fila[1] for fila in conn.execute(sqlalchemy.text("PRAGMA table_info(usuario)"))}
        columnas_usuario_nuevas = {
            'nombre': 'VARCHAR(120)',
            'foto': 'VARCHAR(255)',
        }
        for nombre_columna, tipo_sql in columnas_usuario_nuevas.items():
            if nombre_columna not in columnas_usuario_existentes:
                conn.execute(sqlalchemy.text(f'ALTER TABLE usuario ADD COLUMN {nombre_columna} {tipo_sql}'))
                conn.commit()

CARPETA_FOTOS_PERFIL = os.path.join(basedir, 'static', 'uploads', 'perfil')
os.makedirs(CARPETA_FOTOS_PERFIL, exist_ok=True)
EXTENSIONES_FOTO_PERMITIDAS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


# ==========================================
# FUNCIONES AUXILIARES
# ==========================================

def normalizar_nombre(nombre):
    return ' '.join((nombre or '').split()).strip().lower()


def buscar_cliente_duplicado(nombre, telefono, cedula=None, excluir_id=None):
    nombre_norm = normalizar_nombre(nombre)
    telefono_norm = (telefono or '').strip()
    cedula_norm = (cedula or '').strip()

    query = Cliente.query
    if excluir_id:
        query = query.filter(Cliente.id != excluir_id)

    for cliente in query.all():
        if normalizar_nombre(cliente.nombre) == nombre_norm and nombre_norm:
            return cliente
        if telefono_norm and (cliente.telefono or '').strip() == telefono_norm:
            return cliente
        if cedula_norm and (cliente.cedula or '').strip() == cedula_norm:
            return cliente
    return None


def obtener_multiplicador_meses(modalidad):
    mod = (modalidad or '').upper()
    if 'BIMESTRAL' in mod:
        return 2.0
    elif 'TRIMESTRAL' in mod:
        return 3.0
    elif 'QUINCENAL' in mod:
        return 15.0 / 30.0
    elif 'SEMANAL' in mod:
        return 7.0 / 30.0
    elif 'DIARIO' in mod:
        return 1.0 / 30.0
    else:  
        return 1.0


def calcular_fecha_vencimiento(f_base, index, mod):
    mod_upper = (mod or '').upper()
    if 'DIARIO' in mod_upper:
        return (f_base + timedelta(days=index)).strftime('%Y-%m-%d')
    elif 'SEMANAL' in mod_upper:
        return (f_base + timedelta(days=7 * index)).strftime('%Y-%m-%d')
    elif 'QUINCENAL' in mod_upper:
        return (f_base + timedelta(days=15 * index)).strftime('%Y-%m-%d')
    elif 'BIMESTRAL' in mod_upper:
        meses_totales = f_base.month - 1 + (2 * index)
        anio = f_base.year + meses_totales // 12
        mes = meses_totales % 12 + 1
        dia = min(f_base.day, [31, 29 if anio % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes-1])
        return date(anio, mes, dia).strftime('%Y-%m-%d')
    elif 'TRIMESTRAL' in mod_upper:
        meses_totales = f_base.month - 1 + (3 * index)
        anio = f_base.year + meses_totales // 12
        mes = meses_totales % 12 + 1
        dia = min(f_base.day, [31, 29 if anio % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes-1])
        return date(anio, mes, dia).strftime('%Y-%m-%d')
    else:
        meses_totales = f_base.month - 1 + index
        anio = f_base.year + meses_totales // 12
        mes = meses_totales % 12 + 1
        dia = min(f_base.day, [31, 29 if anio % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes-1])
        return date(anio, mes, dia).strftime('%Y-%m-%d')


def validar_password(pwd):
    if len(pwd) < 8:
        return 'La contraseña debe tener al menos 8 caracteres.'
    if not any(c.isupper() for c in pwd):
        return 'Debe incluir al menos una letra mayúscula.'
    if not any(c.islower() for c in pwd):
        return 'Debe incluir al menos una letra minúscula.'
    if not any(c.isdigit() for c in pwd):
        return 'Debe incluir al menos un número.'
    return None


# ==========================================
# RUTAS DE AUTENTICACIÓN Y REGISTRO DIRECTO
# ==========================================

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = Usuario.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            session.permanent = True
            session['user_id'] = user.id
            return redirect(url_for('dashboard'))
        flash('Correo o contraseña incorrectos.', 'error')
    return render_template('login.html')


@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash('Invalido: Las contraseñas no coinciden.', 'error')
            return redirect(url_for('registro'))

        error_pwd = validar_password(password)
        if error_pwd:
            flash(error_pwd, 'error')
            return redirect(url_for('registro'))

        user_exist = Usuario.query.filter_by(email=email).first()
        if user_exist:
            flash('Este correo ya está registrado.', 'error')
            return redirect(url_for('registro'))

        nuevo_usuario = Usuario(
            email=email,
            password=generate_password_hash(password)
        )
        db.session.add(nuevo_usuario)
        db.session.commit()

        flash('¡Cuenta creada exitosamente! Ya puedes iniciar sesión.', 'success')
        return redirect(url_for('login'))

    return render_template('registro.html')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Sesión cerrada correctamente.', 'success')
    return redirect(url_for('login'))


def extension_permitida(nombre_archivo):
    return '.' in nombre_archivo and nombre_archivo.rsplit('.', 1)[1].lower() in EXTENSIONES_FOTO_PERMITIDAS


@app.route('/perfil/actualizar', methods=['POST'])
def actualizar_perfil():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    usuario = db.session.get(Usuario, session['user_id'])
    if not usuario:
        return redirect(url_for('login'))

    nombre = request.form.get('nombre', '').strip()
    usuario.nombre = nombre

    archivo = request.files.get('foto')
    if archivo and archivo.filename and extension_permitida(archivo.filename):
        extension = archivo.filename.rsplit('.', 1)[1].lower()
        nombre_archivo = secure_filename(f'usuario_{usuario.id}.{extension}')
        ruta_guardado = os.path.join(CARPETA_FOTOS_PERFIL, nombre_archivo)

        if usuario.foto and usuario.foto != nombre_archivo:
            ruta_anterior = os.path.join(CARPETA_FOTOS_PERFIL, usuario.foto)
            if os.path.exists(ruta_anterior):
                os.remove(ruta_anterior)

        archivo.save(ruta_guardado)
        usuario.foto = nombre_archivo

    db.session.commit()
    flash('Perfil actualizado correctamente.', 'success')
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/perfil/eliminar_foto', methods=['POST'])
def eliminar_foto_perfil():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    usuario = db.session.get(Usuario, session['user_id'])
    if usuario and usuario.foto:
        ruta_foto = os.path.join(CARPETA_FOTOS_PERFIL, usuario.foto)
        if os.path.exists(ruta_foto):
            os.remove(ruta_foto)
        usuario.foto = None
        db.session.commit()
        flash('Foto de perfil eliminada.', 'success')

    return redirect(request.referrer or url_for('dashboard'))


@app.route('/static/uploads/perfil/<path:nombre_archivo>')
def foto_perfil(nombre_archivo):
    return send_from_directory(CARPETA_FOTOS_PERFIL, nombre_archivo)


@app.route('/verificar-codigo', methods=['GET', 'POST'])
def verificar_codigo():
    return redirect(url_for('login'))


@app.route('/reenviar-codigo', methods=['POST'])
def reenviar_codigo():
    return redirect(url_for('login'))


# ==========================================
# RUTAS DEL SISTEMA PRINCIPAL
# ==========================================

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    clientes_count = Cliente.query.count()
    prestamos_activos_count = Prestamo.query.filter_by(estado='Activo').count()

    capital_prestado = db.session.query(db.func.sum(Prestamo.capital_inicial)).filter_by(estado='Activo').scalar() or 0.0

    prestamos_activos_lista = Prestamo.query.filter_by(estado='Activo').all()
    
    total_interes_proyectado = 0.0
    for p in prestamos_activos_lista:
        total_interes_proyectado += sum(c.interes_esperado for c in p.cuotas)

    hoy_str = date.today().strftime('%Y-%m-%d')
    
    todas_las_cuentas_pendientes = []
    cuotas_pendientes_hoy = 0
    en_mora = 0

    for p in prestamos_activos_lista:
        cuotas_pendientes = [c for c in p.cuotas if c.estado == 'Pendiente']
        if not cuotas_pendientes:
            continue

        proxima_cuota = min(cuotas_pendientes, key=lambda c: c.numero_cuota)

        vencida = proxima_cuota.fecha_vencimiento < hoy_str
        vence_hoy = proxima_cuota.fecha_vencimiento == hoy_str
        info_cuota = {
            'prestamo_id': p.id,
            'cliente': p.cliente.nombre.lower(),
            'cliente_display': p.cliente.nombre,
            'telefono': p.cliente.telefono,
            'cuota_num': proxima_cuota.numero_cuota,
            'valor': proxima_cuota.valor_cuota,
            'vencimiento': proxima_cuota.fecha_vencimiento,
            'vencida': vencida,
            'vence_hoy': vence_hoy,
        }
        todas_las_cuentas_pendientes.append(info_cuota)

        if vence_hoy:
            cuotas_pendientes_hoy += 1
        if vencida:
            en_mora += 1

    todas_las_cuentas_pendientes.sort(key=lambda c: c['vencimiento'])
    cuentas_por_cobrar_hoy = todas_las_cuentas_pendientes

    cobrado_hoy = (
        db.session.query(db.func.sum(Pago.total_pago))
        .filter_by(fecha=hoy_str)
        .scalar()
        or 0.0
    )

    ingresos_meses = [0.0] * 12
    todos_los_pagos = Pago.query.all()
    for p in todos_los_pagos:
        try:
            partes_fecha = p.fecha.split('-')
            if len(partes_fecha) >= 2:
                mes = int(partes_fecha[1])
                if 1 <= mes <= 12:
                    ingresos_meses[mes - 1] += p.total_pago
        except Exception:
            pass

    prestamos = Prestamo.query.all()
    clientes = Cliente.query.all()

    return render_template(
        'dashboard.html',
        clientes_count=clientes_count,
        prestamos_activos=prestamos_activos_count,
        capital_prestado=capital_prestado,
        total_interes_proyectado=total_interes_proyectado,
        cobros_hoy=cobrado_hoy,
        cuentas_por_cobrar=cuentas_por_cobrar_hoy,
        todas_pendientes=todas_las_cuentas_pendientes,
        cuotas_pendientes_hoy=cuotas_pendientes_hoy,
        en_mora=en_mora,
        hoy_str=hoy_str,
        ingresos_meses=ingresos_meses,
        prestamos=prestamos,
        clientes=clientes,
    )


# --- MÓDULO CLIENTES ---
@app.route('/clientes')
def clientes():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    lista_clientes = Cliente.query.all()
    return render_template('clientes.html', clientes=lista_clientes)


@app.route('/clientes/nuevo', methods=['GET', 'POST'])
def agregar_cliente():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        # 'origen' indica desde dónde se envió el formulario:
        # 'modal'  -> modal de "Nuevo Cliente" dentro de clientes.html
        # 'pagina' -> formulario completo de agregar_cliente.html
        origen = request.form.get('origen', 'pagina')

        def redireccion_error():
            """Si el error viene del modal de Clientes, nos quedamos en Clientes
            (reabriendo el modal). Si viene de la página completa, nos quedamos ahí."""
            if origen == 'modal':
                return redirect(url_for('clientes', abrir_modal=1))
            return redirect(url_for('agregar_cliente'))

        nombre = request.form.get('nombre')
        apellidos = request.form.get('apellidos', '')
        nombre_completo = f"{nombre} {apellidos}".strip()
        telefono = request.form.get('telefono')
        # La página completa envía el campo como 'identificacion'; el modal lo envía como 'cedula'.
        cedula = (request.form.get('cedula') or request.form.get('identificacion') or '').strip()
        direccion = request.form.get('direccion', '').strip()
        ocupacion = request.form.get('ocupacion', '').strip()
        fecha_nacimiento = request.form.get('fecha_nacimiento', '').strip()
        
        if not nombre or not telefono:
            flash('Faltan datos obligatorios (Nombre o Teléfono).', 'error')
            return redireccion_error()

        cliente_existente = buscar_cliente_duplicado(nombre_completo, telefono, cedula)
        if cliente_existente:
            # CORRECCIÓN: Se mantiene en la misma pantalla desde la que se envió el formulario
            flash(f'Ya existe un cliente registrado con ese nombre, teléfono o cédula: "{cliente_existente.nombre}" (#{cliente_existente.id}). No se creó un duplicado.', 'warning')
            return redireccion_error()
            
        nuevo_cliente = Cliente(
            nombre=nombre_completo,
            telefono=telefono,
            cedula=cedula or None,
            direccion=direccion or None,
            ocupacion=ocupacion or None,
            fecha_nacimiento=fecha_nacimiento or None,
        )
        db.session.add(nuevo_cliente)
        db.session.commit()
        
        flash('¡Cliente registrado exitosamente!', 'success')
        return redirect(url_for('clientes'))
        
    return render_template('agregar_cliente.html')


@app.route('/clientes/borrar/<int:id>', methods=['GET', 'POST'], endpoint='eliminar_cliente')
def borrar_cliente(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    cliente = Cliente.query.get_or_404(id)
    db.session.delete(cliente)
    db.session.commit()
    flash('Cliente eliminado correctamente.', 'success')
    return redirect(url_for('clientes'))


# --- MÓDULO PRÉSTAMOS ---
@app.route('/prestamos')
def prestamos():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    lista_prestamos = Prestamo.query.all()
    prestamos_activos = Prestamo.query.filter_by(estado='Activo').count()
    capital_prestado = db.session.query(db.func.sum(Prestamo.capital_inicial)).scalar() or 0.0
    cobros_hoy = 0.0 
    clientes_count = Cliente.query.count()

    return render_template(
        'prestamos.html', 
        prestamos=lista_prestamos,
        prestamos_activos=prestamos_activos,
        capital_prestado=capital_prestado,
        cobros_hoy=cobros_hoy,
        clientes_count=clientes_count,
        clientes=Cliente.query.order_by(Cliente.nombre.asc()).all()
    )


@app.route('/nuevo_prestamo', methods=['POST'])
def nuevo_prestamo():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cliente_id = request.form.get('cliente_id')
    nombre = request.form.get('nombre')
    telefono = request.form.get('telefono')
    cedula = request.form.get('cedula', '').strip()

    cliente = None
    if cliente_id and cliente_id != 'nuevo':
        cliente = db.session.get(Cliente, cliente_id)

    if not cliente and nombre and telefono:
        cliente = buscar_cliente_duplicado(nombre, telefono, cedula)
        if not cliente:
            cliente = Cliente(
                nombre=' '.join(nombre.split()).strip(),
                telefono=telefono,
                cedula=cedula or None,
            )
            db.session.add(cliente)
            db.session.commit()
        else:
            flash(f'Ya existía un cliente con esos datos ("{cliente.nombre}"), se usó ese registro en vez de crear uno nuevo.', 'success')

    if not cliente:
        flash('Debe seleccionar o registrar un cliente válido.', 'error')
        return redirect(url_for('prestamos'))

    try:
        capital_raw = request.form.get('capital')
        capital = float(capital_raw) if capital_raw and capital_raw.strip() != '' else 0.0

        tasa_raw = request.form.get('tasa')
        tasa = float(tasa_raw) if tasa_raw and tasa_raw.strip() != '' else 0.0

        cuotas_raw = request.form.get('cuotas')
        if cuotas_raw and cuotas_raw.strip() != '':
            cuotas_cant = int(cuotas_raw)
        else:
            cuotas_cant = None
    except ValueError:
        flash('Capital, tasa y cuotas deben ser valores numéricos válidos.', 'error')
        return redirect(url_for('prestamos'))

    if capital <= 0:
        flash('El capital del préstamo debe ser mayor a cero.', 'error')
        return redirect(url_for('prestamos'))

    modalidad = request.form.get('modalidad', 'MENSUAL')
    tipo_amortizacion = request.form.get('tipo_amortizacion', 'interes_fijo')
    proximo_pago = request.form.get('proximo_pago')
    
    mora_raw = request.form.get('mora')
    porcentaje_mora = float(mora_raw) if mora_raw and mora_raw.strip() != '' else 0.0

    comision_raw = request.form.get('comision')
    porcentaje_comision = float(comision_raw) if comision_raw and comision_raw.strip() != '' else 0.0

    codeudor_nombre = request.form.get('codeudor_nombre')
    codeudor_identificacion = request.form.get('codeudor_identificacion')
    codeudor_telefono = request.form.get('codeudor_telefono')
    codeudor_direccion = request.form.get('codeudor_direccion')

    prestamo = Prestamo(
        cliente_id=cliente.id,
        capital_inicial=capital,
        capital_actual=capital,
        tasa_interes=tasa,
        cuotas_totales=cuotas_cant,
        modalidad=modalidad,
        tipo_amortizacion=tipo_amortizacion,
        porcentaje_mora=porcentaje_mora,
        porcentaje_comision=porcentaje_comision,
        codeudor_nombre=codeudor_nombre,
        codeudor_identificacion=codeudor_identificacion,
        codeudor_telefono=codeudor_telefono,
        codeudor_direccion=codeudor_direccion,
        proximo_pago=proximo_pago,
        estado='Activo',
    )
    db.session.add(prestamo)
    db.session.commit()

    fecha_base = datetime.strptime(proximo_pago, '%Y-%m-%d')
    multiplicador_meses = obtener_multiplicador_meses(modalidad)
    i_tasa = (tasa / 100.0) * multiplicador_meses

    if cuotas_cant is None or cuotas_cant <= 0:
        val_cuota = capital * i_tasa
        interes_por_cuota = val_cuota
        cap_cuota = 0.0
        nueva_cuota = CuotaPrestamo(
            prestamo_id=prestamo.id,
            numero_cuota=1,
            fecha_vencimiento=proximo_pago,
            valor_cuota=val_cuota,
            interes_esperado=interes_por_cuota,
            capital_esperado=cap_cuota,
            estado='Pendiente'
        )
        db.session.add(nueva_cuota)

    elif tipo_amortizacion == 'cuota_fija' or tipo_amortizacion == 'francesa':
        n = cuotas_cant
        if i_tasa > 0:
            val_cuota = capital * (i_tasa * (1 + i_tasa)**n) / ((1 + i_tasa)**n - 1)
        else:
            val_cuota = capital / n

        capital_pendiente = capital

        for c_num in range(1, cuotas_cant + 1):
            fecha_venc = calcular_fecha_vencimiento(fecha_base, c_num, modalidad)

            interes_esperado = capital_pendiente * i_tasa
            capital_esperado = val_cuota - interes_esperado
            
            if c_num == cuotas_cant:
                capital_esperado = capital_pendiente
                val_cuota = capital_esperado + interes_esperado

            capital_pendiente -= capital_esperado

            nueva_cuota = CuotaPrestamo(
                prestamo_id=prestamo.id,
                numero_cuota=c_num,
                fecha_vencimiento=fecha_venc,
                valor_cuota=round(val_cuota, 2),
                interes_esperado=round(interes_esperado, 2),
                capital_esperado=round(capital_esperado, 2),
                estado='Pendiente'
            )
            db.session.add(nueva_cuota)

    elif tipo_amortizacion.upper() in ['CAPITAL AL FINAL', 'CAPITAL_FINAL']:
        interes_periodico = capital * i_tasa

        for c_num in range(1, cuotas_cant + 1):
            fecha_venc = calcular_fecha_vencimiento(fecha_base, c_num, modalidad)

            if c_num < cuotas_cant:
                capital_esperado = 0.0
                interes_esperado = interes_periodico
                val_cuota = interes_periodico
            else:
                capital_esperado = capital
                interes_esperado = interes_periodico
                val_cuota = capital + interes_periodico

            nueva_cuota = CuotaPrestamo(
                prestamo_id=prestamo.id,
                numero_cuota=c_num,
                fecha_vencimiento=fecha_venc,
                valor_cuota=round(val_cuota, 2),
                interes_esperado=round(interes_esperado, 2),
                capital_esperado=round(capital_esperado, 2),
                estado='Pendiente'
            )
            db.session.add(nueva_cuota)

    else:
        interes_total_esperado = capital * (tasa / 100.0)
        cap_cuota = capital / cuotas_cant
        interes_por_cuota = interes_total_esperado / cuotas_cant
        val_cuota_calculada = cap_cuota + interes_por_cuota

        for i in range(1, cuotas_cant + 1):
            fecha_venc = calcular_fecha_vencimiento(fecha_base, i, modalidad)

            nueva_cuota = CuotaPrestamo(
                prestamo_id=prestamo.id,
                numero_cuota=i,
                fecha_vencimiento=fecha_venc,
                valor_cuota=round(val_cuota_calculada, 2),
                interes_esperado=round(interes_por_cuota, 2),
                capital_esperado=round(cap_cuota, 2),
                estado='Pendiente'
            )
            db.session.add(nueva_cuota)

    db.session.commit()

    flash('Préstamo y calendario de cuotas generado con éxito.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/prestamo/<int:id>')
def detalle_prestamo(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    prestamo = Prestamo.query.get_or_404(id)
    mult_meses = obtener_multiplicador_meses(prestamo.modalidad)

    # Intereses Acumulados Cobrados: suma de los intereses realmente pagados
    # (historial de pagos), no un "total esperado" que no existe en créditos
    # indefinidos (cuotas_totales = None / ∞), donde el interés se sigue
    # generando cuota tras cuota sin un total fijo.
    intereses_acumulados_cobrados = sum(p.interes for p in prestamo.pagos)

    total_abonado = sum(p.total_pago for p in prestamo.pagos)

    # Saldo Total Pendiente = capital vigente + interés de la(s) cuota(s)
    # pendiente(s), es decir, lo que realmente se debe pagar en este momento.
    # En créditos indefinidos solo existe una cuota pendiente a la vez (se va
    # generando cuota por cuota), así que esto ya refleja capital + interés
    # del ciclo actual sin inventar un total infinito.
    saldo_total_pendiente = prestamo.capital_actual + sum(
        c.interes_esperado for c in prestamo.cuotas if c.estado == 'Pendiente'
    )

    cuota_pendiente_actual = next((c for c in prestamo.cuotas if c.estado == 'Pendiente'), None)

    return render_template(
        'detalle_prestamo.html', 
        prestamo=prestamo,
        total_intereses=intereses_acumulados_cobrados,
        total_abonado=total_abonado,
        saldo_total_pendiente=saldo_total_pendiente,
        cuota_pendiente_actual=cuota_pendiente_actual
    )


@app.route('/prestamo/<int:id>/abonar', methods=['POST'])
def registrar_abono(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    prestamo = Prestamo.query.get_or_404(id)
    concepto = request.form.get('concepto', 'Abono / Pago')

    try:
        total_pago_raw = request.form.get('total_pago')
        total_pago = float(total_pago_raw) if total_pago_raw and total_pago_raw.strip() != '' else 0.0

        capital_raw = request.form.get('capital')
        capital_abonado = float(capital_raw) if capital_raw and capital_raw.strip() != '' else 0.0

        interes_raw = request.form.get('interes')
        interes_abonado = float(interes_raw) if interes_raw and interes_raw.strip() != '' else 0.0

        mora_raw = request.form.get('mora')
        mora_abonada = float(mora_raw) if mora_raw and mora_raw.strip() != '' else 0.0
    except ValueError:
        flash('Los valores del pago deben ser numéricos válidos.', 'error')
        return redirect(url_for('detalle_prestamo', id=id))

    if total_pago <= 0:
        flash('El total del pago debe ser mayor a cero.', 'error')
        return redirect(url_for('detalle_prestamo', id=id))

    fecha_pago = request.form.get('fecha', date.today().strftime('%Y-%m-%d'))
    modo_pago = request.form.get('modo', 'cuota')

    cuota_pendiente = CuotaPrestamo.query.filter_by(prestamo_id=prestamo.id, estado='Pendiente').order_by(CuotaPrestamo.numero_cuota.asc()).first()

    # Si el modo es "Pagar Cuota Actual", el pago SIEMPRE debe usar el
    # capital/interés real calculado por el servidor para esa cuota (según el
    # capital vigente en ese momento), sin importar qué valores haya
    # pre-cargado o enviado el formulario. Esto evita que un abono a capital
    # hecho el mismo día corrompa el monto de la cuota ordinaria siguiente.
    # Este ajuste NO debe aplicarse en "Pagar Todo el Capital", porque ahí el
    # total real a pagar es el saldo completo (capital + interés pendiente),
    # no solo el valor de una cuota individual.
    if cuota_pendiente and modo_pago == 'cuota':
        capital_abonado = cuota_pendiente.capital_esperado or 0.0
        interes_abonado = cuota_pendiente.interes_esperado or 0.0
        total_pago = capital_abonado + interes_abonado + mora_abonada
    
    nuevo_pago = Pago(
        prestamo_id=prestamo.id,
        concepto=concepto,
        fecha=fecha_pago,
        fecha_vencimiento=prestamo.proximo_pago,
        total_pago=total_pago,
        capital=capital_abonado,
        interes=interes_abonado,
        mora=mora_abonada
    )
    db.session.add(nuevo_pago)
    
    if capital_abonado > 0:
        prestamo.capital_actual = max(0.0, prestamo.capital_actual - capital_abonado)
        if prestamo.capital_actual <= 0:
            prestamo.estado = 'Pagado'

    if cuota_pendiente:
        cuota_pendiente.estado = 'Pagada'

    if prestamo.capital_actual <= 0:
        # Deuda cancelada por completo: no tiene sentido avanzar la fecha de
        # próximo pago ni generar una cuota nueva, porque ya no hay nada
        # pendiente por cobrar.
        db.session.commit()
        flash('¡Deuda cancelada en su totalidad! El cliente quedó al día.', 'success')
        return redirect(url_for('detalle_prestamo', id=prestamo.id))

    if cuota_pendiente:
        f_actual = datetime.strptime(prestamo.proximo_pago, '%Y-%m-%d')
        mod = prestamo.modalidad.upper()
        
        if 'DIARIO' in mod:
            nueva_fecha = f_actual + timedelta(days=1)
        elif 'SEMANAL' in mod:
            nueva_fecha = f_actual + timedelta(days=7)
        elif 'QUINCENAL' in mod:
            nueva_fecha = f_actual + timedelta(days=15)
        elif 'BIMESTRAL' in mod:
            meses_totales = f_actual.month - 1 + 2
            anio = f_actual.year + meses_totales // 12
            mes = meses_totales % 12 + 1
            dia = min(f_actual.day, [31, 29 if anio % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes-1])
            nueva_fecha = date(anio, mes, dia)
        elif 'TRIMESTRAL' in mod:
            meses_totales = f_actual.month - 1 + 3
            anio = f_actual.year + meses_totales // 12
            mes = meses_totales % 12 + 1
            dia = min(f_actual.day, [31, 29 if anio % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes-1])
            nueva_fecha = date(anio, mes, dia)
        else:
            meses_totales = f_actual.month - 1 + 1
            anio = f_actual.year + meses_totales // 12
            mes = meses_totales % 12 + 1
            dia = min(f_actual.day, [31, 29 if anio % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes-1])
            nueva_fecha = date(anio, mes, dia)
            
        prestamo.proximo_pago = nueva_fecha.strftime('%Y-%m-%d')

        # En créditos indefinidos (sin número de cuotas fijo) siempre se debe
        # generar la siguiente cuota de interés, sin importar la etiqueta de
        # tipo_amortizacion que tenga el préstamo (CAPITAL AL FINAL, cuota
        # fija, etc.) — todos se cobran ciclo a ciclo de la misma forma.
        sin_cuotas_definidas = not prestamo.cuotas_totales or prestamo.cuotas_totales <= 0
        if sin_cuotas_definidas and prestamo.capital_actual > 0:
            multiplicador_meses = obtener_multiplicador_meses(prestamo.modalidad)
            i_tasa = (prestamo.tasa_interes / 100.0) * multiplicador_meses
            interes_periodico = prestamo.capital_actual * i_tasa

            siguiente_numero = (cuota_pendiente.numero_cuota or 0) + 1
            cuota_siguiente = CuotaPrestamo(
                prestamo_id=prestamo.id,
                numero_cuota=siguiente_numero,
                fecha_vencimiento=prestamo.proximo_pago,
                valor_cuota=round(interes_periodico, 2),
                interes_esperado=round(interes_periodico, 2),
                capital_esperado=0.0,
                estado='Pendiente'
            )
            db.session.add(cuota_siguiente)

    db.session.commit()
    flash('Pago registrado y ciclo de cobro actualizado correctamente.', 'success')
    return redirect(url_for('detalle_prestamo', id=prestamo.id))


def regenerar_amortizacion_pendiente(prestamo, preservar_cuota_actual=False):
    """Recalcula las cuotas pendientes de un préstamo (CUOTA_FIJA/FRANCESA,
    CAPITAL AL FINAL o interés fijo, con o sin número de cuotas definido) en
    base al capital_actual vigente, dejando intactas las cuotas ya pagadas.
    Sirve tanto para incrementos de capital (ajustar capital) como para
    abonos que lo reducen (abonar a capital).

    Si preservar_cuota_actual=True, la cuota pendiente más próxima (la que
    ya estaba en curso cuando se hizo el abono) NO se modifica, porque su
    interés ya se generó sobre el capital vigente antes del abono. Solo las
    cuotas futuras (aún no generadas) se recalculan sobre el nuevo capital."""
    mult_meses = obtener_multiplicador_meses(prestamo.modalidad)
    i_tasa = (prestamo.tasa_interes / 100.0) * mult_meses

    cuotas_pagadas = [c for c in prestamo.cuotas if c.estado == 'Pagada']
    cuotas_pendientes = sorted([c for c in prestamo.cuotas if c.estado == 'Pendiente'], key=lambda c: c.numero_cuota)
    ultimo_numero_pagado = max([c.numero_cuota for c in cuotas_pagadas], default=0)

    cuota_preservada = None
    if preservar_cuota_actual and cuotas_pendientes:
        cuota_preservada = cuotas_pendientes[0]
        cuotas_pendientes = cuotas_pendientes[1:]
        ultimo_numero_pagado = cuota_preservada.numero_cuota

    fecha_base_str = cuota_preservada.fecha_vencimiento if cuota_preservada else (prestamo.proximo_pago or date.today().strftime('%Y-%m-%d'))
    fecha_base = datetime.strptime(fecha_base_str, '%Y-%m-%d')

    tipo = prestamo.tipo_amortizacion.upper()
    sin_cuotas_definidas = not prestamo.cuotas_totales or prestamo.cuotas_totales <= 0

    if prestamo.capital_actual <= 0:
        for c in cuotas_pendientes:
            db.session.delete(c)
        return

    if sin_cuotas_definidas:
        interes_periodico = prestamo.capital_actual * i_tasa
        if cuotas_pendientes:
            cuota_actual = cuotas_pendientes[0]
            cuota_actual.interes_esperado = round(interes_periodico, 2)
            cuota_actual.valor_cuota = round(interes_periodico, 2)
            cuota_actual.capital_esperado = 0.0
        elif not cuota_preservada:
            nueva_cuota = CuotaPrestamo(
                prestamo_id=prestamo.id,
                numero_cuota=ultimo_numero_pagado + 1,
                fecha_vencimiento=fecha_base_str,
                valor_cuota=round(interes_periodico, 2),
                interes_esperado=round(interes_periodico, 2),
                capital_esperado=0.0,
                estado='Pendiente'
            )
            db.session.add(nueva_cuota)
        # Si hay cuota_preservada y no quedan más pendientes, no se genera nada
        # nuevo todavía: la siguiente cuota se creará al pagar la preservada,
        # ya usando el capital_actual actualizado.
        return

    cuotas_restantes_cant = prestamo.cuotas_totales - len(cuotas_pagadas) - (1 if cuota_preservada else 0)
    if cuotas_restantes_cant <= 0:
        for c in cuotas_pendientes:
            db.session.delete(c)
        return

    for c in cuotas_pendientes:
        db.session.delete(c)

    capital_a_amortizar = prestamo.capital_actual - (cuota_preservada.capital_esperado if cuota_preservada else 0.0)
    if capital_a_amortizar < 0:
        capital_a_amortizar = 0.0

    if capital_a_amortizar <= 0:
        return

    if tipo in ['CUOTA_FIJA', 'FRANCESA']:
        n = cuotas_restantes_cant
        if i_tasa > 0:
            val_cuota = capital_a_amortizar * (i_tasa * (1 + i_tasa) ** n) / ((1 + i_tasa) ** n - 1)
        else:
            val_cuota = capital_a_amortizar / n

        capital_pendiente = capital_a_amortizar
        for idx in range(1, n + 1):
            c_num = ultimo_numero_pagado + idx
            offset_fecha = 0 if cuota_preservada else 1
            fecha_venc = fecha_base_str if (idx == 1 and not cuota_preservada) else calcular_fecha_vencimiento(fecha_base, idx - offset_fecha, prestamo.modalidad)

            interes_esperado = capital_pendiente * i_tasa
            capital_esperado = val_cuota - interes_esperado

            if idx == n:
                capital_esperado = capital_pendiente
                val_cuota_final = capital_esperado + interes_esperado
            else:
                val_cuota_final = val_cuota

            capital_pendiente -= capital_esperado

            nueva_cuota = CuotaPrestamo(
                prestamo_id=prestamo.id,
                numero_cuota=c_num,
                fecha_vencimiento=fecha_venc,
                valor_cuota=round(val_cuota_final, 2),
                interes_esperado=round(interes_esperado, 2),
                capital_esperado=round(capital_esperado, 2),
                estado='Pendiente'
            )
            db.session.add(nueva_cuota)

    elif tipo in ['CAPITAL AL FINAL', 'CAPITAL_FINAL']:
        n = cuotas_restantes_cant
        interes_periodico = capital_a_amortizar * i_tasa

        for idx in range(1, n + 1):
            c_num = ultimo_numero_pagado + idx
            offset_fecha = 0 if cuota_preservada else 1
            fecha_venc = fecha_base_str if (idx == 1 and not cuota_preservada) else calcular_fecha_vencimiento(fecha_base, idx - offset_fecha, prestamo.modalidad)

            if idx < n:
                capital_esperado = 0.0
                interes_esperado = interes_periodico
                val_cuota = interes_periodico
            else:
                capital_esperado = capital_a_amortizar
                interes_esperado = interes_periodico
                val_cuota = capital_a_amortizar + interes_periodico

            nueva_cuota = CuotaPrestamo(
                prestamo_id=prestamo.id,
                numero_cuota=c_num,
                fecha_vencimiento=fecha_venc,
                valor_cuota=round(val_cuota, 2),
                interes_esperado=round(interes_esperado, 2),
                capital_esperado=round(capital_esperado, 2),
                estado='Pendiente'
            )
            db.session.add(nueva_cuota)

    else:
        n = cuotas_restantes_cant
        interes_total_esperado = capital_a_amortizar * (prestamo.tasa_interes / 100.0)
        cap_cuota = capital_a_amortizar / n
        interes_por_cuota = interes_total_esperado / n
        val_cuota_calculada = cap_cuota + interes_por_cuota

        for idx in range(1, n + 1):
            c_num = ultimo_numero_pagado + idx
            offset_fecha = 0 if cuota_preservada else 1
            fecha_venc = fecha_base_str if (idx == 1 and not cuota_preservada) else calcular_fecha_vencimiento(fecha_base, idx - offset_fecha, prestamo.modalidad)

            nueva_cuota = CuotaPrestamo(
                prestamo_id=prestamo.id,
                numero_cuota=c_num,
                fecha_vencimiento=fecha_venc,
                valor_cuota=round(val_cuota_calculada, 2),
                interes_esperado=round(interes_por_cuota, 2),
                capital_esperado=round(cap_cuota, 2),
                estado='Pendiente'
            )
            db.session.add(nueva_cuota)


@app.route('/prestamo/<int:id>/ajustar_capital', methods=['POST'])
def ajustar_capital(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    prestamo = Prestamo.query.get_or_404(id)

    if prestamo.estado != 'Activo':
        flash('Solo se puede ajustar el capital de préstamos activos.', 'error')
        return redirect(url_for('detalle_prestamo', id=id))

    try:
        monto_raw = request.form.get('monto_adicional')
        monto_adicional = float(monto_raw) if monto_raw and monto_raw.strip() != '' else 0.0
    except ValueError:
        flash('El monto adicional debe ser un valor numérico válido.', 'error')
        return redirect(url_for('detalle_prestamo', id=id))

    if monto_adicional <= 0:
        flash('El monto adicional a prestar debe ser mayor a cero.', 'error')
        return redirect(url_for('detalle_prestamo', id=id))

    prestamo.capital_inicial += monto_adicional
    prestamo.capital_actual += monto_adicional

    # preservar_cuota_actual=False: la cuota pendiente en curso también se
    # recalcula con el nuevo capital (más alto) tras el ajuste, para que la
    # próxima cuota sugerida refleje el interés correcto sobre la deuda
    # actual (p. ej. si el capital sube de $700,000 a $1,700,000 al 10%, la
    # próxima cuota debe ser $170,000 y no seguir mostrando el interés
    # calculado sobre el capital anterior).
    regenerar_amortizacion_pendiente(prestamo, preservar_cuota_actual=False)

    db.session.commit()
    flash(f'Capital ajustado: se sumaron ${monto_adicional:,.2f} al préstamo y la amortización se recalculó automáticamente.', 'success')
    return redirect(url_for('detalle_prestamo', id=prestamo.id))


@app.route('/prestamo/<int:id>/abonar_capital', methods=['POST'])
def abonar_capital(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    prestamo = Prestamo.query.get_or_404(id)

    if prestamo.estado != 'Activo':
        flash('Solo se pueden registrar abonos a capital en préstamos activos.', 'error')
        return redirect(url_for('detalle_prestamo', id=id))

    try:
        monto_raw = request.form.get('monto_abono')
        monto_abono = float(monto_raw) if monto_raw and monto_raw.strip() != '' else 0.0
    except ValueError:
        flash('El monto del abono debe ser un valor numérico válido.', 'error')
        return redirect(url_for('detalle_prestamo', id=id))

    if monto_abono <= 0:
        flash('El monto del abono a capital debe ser mayor a cero.', 'error')
        return redirect(url_for('detalle_prestamo', id=id))

    if monto_abono > prestamo.capital_actual:
        monto_abono = prestamo.capital_actual

    fecha_pago = request.form.get('fecha', date.today().strftime('%Y-%m-%d'))

    nuevo_pago = Pago(
        prestamo_id=prestamo.id,
        concepto='ABONO A CAPITAL',
        fecha=fecha_pago,
        fecha_vencimiento=prestamo.proximo_pago,
        total_pago=monto_abono,
        capital=monto_abono,
        interes=0.0,
        mora=0.0
    )
    db.session.add(nuevo_pago)

    prestamo.capital_actual = max(0.0, prestamo.capital_actual - monto_abono)

    if prestamo.capital_actual <= 0:
        prestamo.estado = 'Pagado'

    # preservar_cuota_actual=False: la cuota pendiente en curso también debe
    # recalcularse con el nuevo capital (más bajo) tras el abono, para que el
    # próximo pago de cuota refleje el interés correcto (p. ej. si el capital
    # baja de $1,000,000 a $300,000 al 10%, la próxima cuota debe ser $30,000
    # y no seguir mostrando el interés calculado sobre el capital anterior).
    regenerar_amortizacion_pendiente(prestamo, preservar_cuota_actual=False)

    db.session.commit()
    flash(f'Abono a capital de ${monto_abono:,.2f} registrado. La amortización se recalculó automáticamente.', 'success')
    return redirect(url_for('detalle_prestamo', id=prestamo.id))


# --- MÓDULO PAGOS ---
@app.route('/pagos')
def pagos():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    todos_pagos = Pago.query.all()
    return render_template('pagos.html', pagos=todos_pagos)


@app.route('/pago/<int:id>/recibo')
def ver_recibo_pago(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    pago = Pago.query.get_or_404(id)
    prestamo = pago.prestamo
    
    cuotas_totales = prestamo.cuotas_totales
    cuotas_pendientes = sum(1 for c in prestamo.cuotas if c.estado == 'Pendiente')
    cuotas_pagadas = sum(1 for c in prestamo.cuotas if c.estado == 'Pagada')
    
    return render_template(
        'recibo_pago.html', 
        pago=pago, 
        prestamo=prestamo,
        cuotas_pendientes=cuotas_pendientes,
        cuotas_pagadas=cuotas_pagadas,
        cuotas_totales=cuotas_totales
    )


@app.route('/pagos/borrar/<int:id>', methods=['GET', 'POST'])
def borrar_pago(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    pago = Pago.query.get_or_404(id)
    db.session.delete(pago)
    db.session.commit()
    flash('Registro de pago eliminado correctamente.', 'success')
    return redirect(url_for('pagos'))


@app.route('/cobranza')
def cobranza():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    filtro_estado = request.args.get('filtro_estado', '')
    fecha_filtro = request.args.get('fecha_filtro', '')

    hoy_str = date.today().strftime('%Y-%m-%d')
    prestamos_activos = Prestamo.query.filter_by(estado='Activo').all()

    cobranzas = []
    cuotas_pagadas_total = 0
    cuotas_pendientes_total = 0
    al_dia = 0
    en_mora = 0
    vencen_hoy = 0

    for p in prestamos_activos:
        cuotas_pagadas_total += sum(1 for c in p.cuotas if c.estado == 'Pagada')
        cuotas_pendientes = [c for c in p.cuotas if c.estado == 'Pendiente']
        cuotas_pendientes_total += len(cuotas_pendientes)

        if not cuotas_pendientes:
            continue

        proxima_cuota = min(cuotas_pendientes, key=lambda c: c.numero_cuota)
        vencimiento = proxima_cuota.fecha_vencimiento

        if vencimiento < hoy_str:
            estado_cobro = 'En Mora'
            dias_atraso = (datetime.strptime(hoy_str, '%Y-%m-%d') - datetime.strptime(vencimiento, '%Y-%m-%d')).days
            en_mora += 1
        elif vencimiento == hoy_str:
            estado_cobro = 'Vence Hoy'
            dias_atraso = 0
            vencen_hoy += 1
        else:
            estado_cobro = 'Al Día'
            dias_atraso = 0
            al_dia += 1

        monto_pendiente = sum(c.valor_cuota for c in cuotas_pendientes)

        cobranzas.append({
            'prestamo_id': p.id,
            'cliente_nombre': p.cliente.nombre,
            'telefono': p.cliente.telefono,
            'vencimiento': vencimiento,
            'dias_atraso': dias_atraso,
            'estado': estado_cobro,
            'monto_pendiente': monto_pendiente,
        })

    if filtro_estado == 'hoy':
        cobranzas = [c for c in cobranzas if c['estado'] == 'Vence Hoy']
    elif filtro_estado == 'mora':
        cobranzas = [c for c in cobranzas if c['estado'] == 'En Mora']
    elif filtro_estado == 'promesas':
        cobranzas = []

    if fecha_filtro:
        cobranzas = [c for c in cobranzas if c['vencimiento'] == fecha_filtro]

    cobranzas.sort(key=lambda c: c['vencimiento'])

    total_cartera = len(prestamos_activos)
    cumplidas = cuotas_pagadas_total
    incumplidas = en_mora
    total_cuotas_ref = cuotas_pagadas_total + cuotas_pendientes_total
    cumplimiento = f"{round((cuotas_pagadas_total / total_cuotas_ref) * 100, 1)}%" if total_cuotas_ref > 0 else "0%"

    return render_template(
        'cobranza.html',
        cobranzas=cobranzas,
        total_cartera=total_cartera,
        al_dia=al_dia,
        cumplidas=cumplidas,
        incumplidas=incumplidas,
        vencen_hoy=vencen_hoy,
        cumplimiento=cumplimiento,
    )


@app.route('/caja')
def caja():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    prestamos = Prestamo.query.all()
    capital_prestado = sum(p.capital_inicial for p in prestamos)
    
    total_recaudado = 0
    for p in prestamos:
        for pago in p.pagos:
            total_recaudado += pago.total_pago
            
    balance_caja = total_recaudado - capital_prestado
    
    return render_template(
        'caja.html', 
        capital_prestado=capital_prestado,
        total_recaudado=total_recaudado,
        balance_caja=balance_caja
    )


# ==========================================
# MÓDULO DE SOLICITUDES Y PORTAL PÚBLICO
# ==========================================

@app.route('/solicitudes')
def solicitudes():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    estado_filtro = request.args.get('estado', 'Todos')
    if estado_filtro != 'Todos':
        lista_solicitudes = SolicitudPrestamo.query.filter_by(estado=estado_filtro).all()
    else:
        lista_solicitudes = SolicitudPrestamo.query.all()
        
    pendientes = SolicitudPrestamo.query.filter_by(estado='Pendiente').count()
    contactados = SolicitudPrestamo.query.filter_by(estado='Contactados').count()
    en_revision = SolicitudPrestamo.query.filter_by(estado='En Revisión').count()
    aprobados = SolicitudPrestamo.query.filter_by(estado='Aprobados').count()
    rechazados = SolicitudPrestamo.query.filter_by(estado='Rechazados').count()
    convertidos = SolicitudPrestamo.query.filter_by(estado='Convertidos').count()

    return render_template('solicitudes.html', 
                           solicitudes=lista_solicitudes,
                           pendientes=pendientes,
                           contactados=contactados,
                           en_revision=en_revision,
                           aprobados=aprobados,
                           rechazados=rechazados,
                           convertidos=convertidos)


@app.route('/portal/solicitud', methods=['GET', 'POST'])
def portal_solicitud():
    if request.method == 'POST':
        cuotas_raw = request.form.get('cuotas')
        cuotas_val = int(cuotas_raw) if cuotas_raw and cuotas_raw.strip() != '' else None
        
        monto_raw = request.form.get('monto')
        monto_val = float(monto_raw) if monto_raw and monto_raw.strip() != '' else 0.0

        nueva_sol = SolicitudPrestamo(
            nombre=request.form.get('nombre'),
            telefono=request.form.get('telefono'),
            email=request.form.get('email'),
            monto_solicitado=monto_val,
            cuotas=cuotas_val,
            motivo=request.form.get('motivo'),
            estado='Pendiente'
        )
        db.session.add(nueva_sol)
        db.session.commit()
        flash('¡Solicitud enviada con éxito! Nos pondremos en contacto contigo.', 'success')
        return redirect(url_for('portal_solicitud'))
        
    return render_template('portal_solicitud.html')


@app.route('/solicitud/<int:id>/cambiar_estado/<estado>')
def cambiar_estado_solicitud(id, estado):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    sol = SolicitudPrestamo.query.get_or_404(id)
    sol.estado = estado
    db.session.commit()
    flash(f'Estado de la solicitud actualizado a: {estado}', 'success')
    return redirect(url_for('solicitudes'))


@app.route('/solicitudes/borrar/<int:id>', methods=['GET', 'POST'])
def borrar_solicitud(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    sol = SolicitudPrestamo.query.get_or_404(id)
    db.session.delete(sol)
    db.session.commit()
    flash('Solicitud eliminada correctamente.', 'success')
    return redirect(url_for('solicitudes'))


# ==========================================
# MÓDULO DE RUTAS
# ==========================================

@app.route('/rutas', methods=['GET', 'POST'])
def rutas():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        descripcion = request.form.get('descripcion')
        color = request.form.get('color', 'Azul')
        cobrador = request.form.get('cobrador')
        
        if not nombre:
            flash('El nombre de la ruta es obligatorio.', 'error')
            return redirect(url_for('rutas'))
            
        nueva_ruta = Ruta(
            nombre=nombre,
            descripcion=descripcion,
            color=color,
            cobrador=cobrador,
            estado='Activa'
        )
        db.session.add(nueva_ruta)
        db.session.commit()
        flash('Ruta creada exitosamente.', 'success')
        return redirect(url_for('rutas'))
        
    lista_rutas = Ruta.query.all()
    lista_clientes = Cliente.query.all()
    return render_template('rutas.html', rutas=lista_rutas, clientes=lista_clientes)


@app.route('/ruta/<int:id>')
def detalle_ruta(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    ruta = Ruta.query.get_or_404(id)
    clientes_disponibles = Cliente.query.filter((Cliente.ruta_id == None) | (Cliente.ruta_id != id)).all()
    return render_template('detalle_ruta.html', ruta=ruta, clientes_disponibles=clientes_disponibles)


@app.route('/ruta/<int:ruta_id>/asignar_cliente', methods=['POST'])
def asignar_cliente_ruta(ruta_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    cliente_id = request.form.get('cliente_id')
    cliente = Cliente.query.get_or_404(cliente_id)
    cliente.ruta_id = ruta_id
    db.session.commit()
    flash('Cliente agregado a la ruta correctamente.', 'success')
    return redirect(url_for('detalle_ruta', id=ruta_id))


@app.route('/ruta/remover_cliente/<int:cliente_id>', methods=['GET', 'POST'])
def remover_cliente_ruta(cliente_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    cliente = Cliente.query.get_or_404(cliente_id)
    ruta_id = cliente.ruta_id
    cliente.ruta_id = None
    db.session.commit()
    flash('Cliente retirado de la ruta.', 'success')
    return redirect(url_for('detalle_ruta', id=ruta_id))


@app.route('/rutas/borrar/<int:id>', methods=['GET', 'POST'])
def borrar_ruta(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    ruta = Ruta.query.get_or_404(id)
    db.session.delete(ruta)
    db.session.commit()
    flash('Ruta eliminada correctamente.', 'success')
    return redirect(url_for('rutas'))


@app.route('/prestamos/borrar/<int:id>', methods=['GET', 'POST'], endpoint='eliminar_prestamo')
@app.route('/prestamos/eliminar/<int:id>', methods=['GET', 'POST'], endpoint='eliminar_prestamo_alt')
def borrar_prestamo(id):
    app.logger.info("Eliminando préstamo con ID %s", id)
    if 'user_id' not in session:
        return redirect(url_for('login'))
    prestamo = Prestamo.query.get_or_404(id)
    db.session.delete(prestamo)
    db.session.commit()
    flash('Préstamo eliminado correctamente.', 'success')
    return redirect(url_for('prestamos'))


@app.route('/contratos', methods=['GET'])
def contratos():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    prestamo_id = request.args.get('prestamo_id')
    tipo_contrato = request.args.get('tipo', 'prestamo')
    
    prestamo = None
    if prestamo_id:
        prestamo = Prestamo.query.get_or_404(prestamo_id)
        
    lista_prestamos = Prestamo.query.all()
    return render_template('contratos.html', prestamo=prestamo, lista_prestamos=lista_prestamos, tipo=tipo_contrato)


@app.route('/reportes')
def reportes():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('reportes.html')


# ==========================================
# RUTAS DE EXPORTACIÓN A EXCEL
# ==========================================

@app.route('/exportar-cartera-excel')
def exportar_cartera_excel():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    flash('Módulo de exportación de cartera en desarrollo.', 'info')
    return redirect(url_for('reportes'))


@app.route('/exportar-pagos-excel')
def exportar_pagos_excel():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    flash('Módulo de exportación de pagos en desarrollo.', 'info')
    return redirect(url_for('reportes'))


@app.route('/exportar-morosos-excel')
def exportar_morosos_excel():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    flash('Módulo de exportación de morosos en desarrollo.', 'info')
    return redirect(url_for('reportes'))


# ==========================================
# EJECUCIÓN DE LA APLICACIÓN
# ==========================================

if __name__ == '__main__':
    app.run(debug=True)
