import dbm # No usado, se puede eliminar
from sqlite3 import dbapi2 # No usado, se puede eliminar
from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, session
import mysql.connector
from mysql.connector import Error
import os
from datetime import date, datetime, timedelta

app = Flask(__name__)

app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'una_clave_secreta_muy_larga_y_aleatoria_para_desarrollo_local_2024')

# --- Configuración de la base de datos (tomada de variables de entorno) ---
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_USER = os.environ.get('DB_USER', 'root')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '123456')
DB_NAME = os.environ.get('DB_NAME', 'facturacion_db')

# Función para establecer la conexión a la base de datos
def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        ssl_ca='DigiCertGlobalRootCA.crt.pem'  # Si estás en local con SSL
    )

# --- Rutas de la aplicación ---

@app.route('/')
def home():
    """Redirige al usuario al dashboard si ya está logueado, de lo contrario al login."""
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Maneja el formulario de inicio de sesión, verificando contra la base de datos."""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        if conn is None:
            return render_template('login.html')

        cursor = conn.cursor(dictionary=True)

        try:
            cursor.execute("SELECT id, username, password_plain, first_name, last_name, role FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()

            if user and user['password_plain'] == password:
                session['logged_in'] = True
                session['username'] = user['username']
                session['first_name'] = user['first_name']
                session['last_name'] = user['last_name']
                session['full_name'] = f"{user['first_name']} {user['last_name']}".strip()
                session['role'] = user['role']
                session['user_id'] = user['id']

                flash('¡Inicio de sesión exitoso!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Nombre de usuario o contraseña incorrectos.', 'danger')
        except Error as e:
            flash(f"Error al verificar credenciales: {e}", 'danger')
            print(f"Error de base de datos en login: {e}")
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    return render_template('login.html')

@app.route('/logout')
def logout():
    """Cierra la sesión del usuario."""
    session.pop('username', None)
    session.pop('first_name', None)
    session.pop('last_name', None)
    session.pop('full_name', None)
    session.pop('role', None)
    session.pop('user_id', None)
    session.pop('cart', None)
    flash('Has cerrado sesión exitosamente.', 'info')
    return redirect(url_for('login'))

# --- RUTAS DE DASHBOARD ---

@app.route('/dashboard')
def dashboard():
    """Ruta genérica del dashboard que redirige según el rol."""
    if 'username' not in session:
        flash('Por favor, inicia sesión para acceder a esta página.', 'info')
        return redirect(url_for('login'))

    user_role = session.get('role')

    if not user_role:
        flash('No se pudo determinar tu rol de usuario. Por favor, inicia sesión de nuevo.', 'danger')
        return redirect(url_for('login'))

    if user_role == 'admin':
        return redirect(url_for('admin_dashboard_view'))
    elif user_role == 'employee':
        return redirect(url_for('employee_dashboard_view')) # Redirige al dashboard de inventario por defecto
    else:
        flash('Tu rol de usuario no tiene permisos para acceder a esta sección.', 'danger')
        return redirect(url_for('login'))


# RUTA MODIFICADA: Ahora solo para "Consultar Inventario" (incluye descripción)
@app.route('/employee/dashboard')
def employee_dashboard_view():
    """Dashboard específico para el rol de Empleado (solo para consultar inventario)."""
    if 'username' not in session or session.get('role') != 'employee':
        flash('Acceso denegado. No tienes permisos de empleado.', 'danger')
        return redirect(url_for('login'))

    conn = None
    cursor = None
    products = []
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, name, price, stock, description FROM products ORDER BY id")
            products = cursor.fetchall()
            # Convertir Decimal a float para el JSON (importante para JavaScript)
            for p in products:
                p['price'] = float(p['price'])
    except Error as e:
        flash(f"Error al cargar productos: {e}", 'danger')
        print(f"Error de base de datos al cargar productos: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return render_template('dashboard_employee.html',
                            full_name=session.get('full_name', session['username']),
                            products=products)

# RUTA PARA LA FUNCIONALIDAD de "Crear Nueva Venta" (Punto de Venta)
@app.route('/employee/new_sale')
def new_sale_view():
    """Página del Punto de Venta para empleados."""
    if 'username' not in session or session.get('role') != 'employee':
        flash('Acceso denegado. No tienes permisos de empleado.', 'danger')
        return redirect(url_for('login'))

    conn = None
    cursor = None
    products = []
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, name, price, stock, description FROM products ORDER BY id")
            products = cursor.fetchall()
            # Convertir Decimal a float para el JSON (importante para JavaScript)
            for p in products:
                p['price'] = float(p['price'])
    except Error as e:
        flash(f"Error al cargar productos para la venta: {e}", 'danger')
        print(f"Error de base de datos al cargar productos para la venta: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    current_cart = session.get('cart', [])

    return render_template('pos_sale.html',
                            full_name=session.get('full_name', session['username']),
                            products=products,
                            current_cart=current_cart)

# RUTA para obtener detalles de un producto por AJAX
@app.route('/product_details/<int:product_id>')
def product_details(product_id):
    if 'username' not in session or session.get('role') not in ['admin', 'employee']:
        return jsonify({'success': False, 'message': 'Acceso denegado.'}), 401

    conn = None
    cursor = None
    product = None
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, name, price, stock, description FROM products WHERE id = %s", (product_id,))
            product = cursor.fetchone()
    except Error as e:
        print(f"Error al obtener detalles del producto: {e}")
        return jsonify({'success': False, 'message': 'Error al obtener detalles del producto.'}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    if product:
        # CONVERTIR EL PRECIO A FLOAT explícitamente para JavaScript
        product['price'] = float(product['price'])
        product['stock'] = int(product['stock'])
        product['id'] = int(product['id'])
        return jsonify({'success': True, 'product': product})
    else:
        return jsonify({'success': False, 'message': 'Producto no encontrado.'}), 404

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'No has iniciado sesión.'}), 401

    data = request.get_json()
    product_id = int(data.get('product_id'))
    product_name = data.get('product_name')
    product_price = float(data.get('product_price'))
    quantity_to_add = int(data.get('quantity', 1))

    if not all([product_id, product_name, product_price]):
        return jsonify({'success': False, 'message': 'Datos del producto incompletos.'}), 400

    conn = None
    cursor = None
    new_product_stock = -1

    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Error de conexión a la base de datos.'}), 500

        cursor = conn.cursor(dictionary=True)

        conn.start_transaction()

        cursor.execute("SELECT stock FROM products WHERE id = %s FOR UPDATE", (product_id,))
        product_info = cursor.fetchone()

        if not product_info:
            conn.rollback()
            return jsonify({'success': False, 'message': 'Producto no encontrado en el inventario.'}), 404

        current_stock = product_info['stock']

        if current_stock < quantity_to_add:
            conn.rollback()
            return jsonify({'success': False, 'message': f'Stock insuficiente para "{product_name}". Disponibles: {current_stock}'}), 400

        cursor.execute("UPDATE products SET stock = stock - %s WHERE id = %s", (quantity_to_add, product_id))

        cursor.execute("SELECT stock FROM products WHERE id = %s", (product_id,))
        new_product_stock_info = cursor.fetchone()
        if new_product_stock_info:
            new_product_stock = new_product_stock_info['stock']

        if 'cart' not in session:
            session['cart'] = []

        found = False
        for item in session['cart']:
            if item['product_id'] == product_id:
                item['quantity'] += quantity_to_add
                found = True
                break

        if not found:
            session['cart'].append({
                'product_id': product_id,
                'product_name': product_name,
                'product_price': product_price,
                'quantity': quantity_to_add
            })

        session.modified = True

        conn.commit()

        cart_total = sum(item['product_price'] * item['quantity'] for item in session['cart'])

        flash(f'{product_name} añadido al carrito!', 'success')
        return jsonify({
            'success': True,
            'message': f'{product_name} añadido al carrito.',
            'cart': session['cart'],
            'cart_total': cart_total,
            'product_id': product_id,
            'new_stock': new_product_stock
        })

    except Error as e:
        if conn:
            conn.rollback()
        print(f"Error al añadir producto al carrito o actualizar stock: {e}")
        flash(f"Error al añadir al carrito: {e}", 'danger')
        return jsonify({'success': False, 'message': 'Error interno del servidor al añadir al carrito.'}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


# --- RUTA PARA ELIMINAR PRODUCTO DEL CARRITO ---
@app.route('/remove_from_cart', methods=['POST'])
def remove_from_cart():
    """Ruta para eliminar un producto del carrito de la sesión y reintegrar su stock."""
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'No has iniciado sesión.'}), 401

    data = request.get_json()
    product_id_to_remove = int(data.get('product_id'))

    conn = None
    cursor = None
    quantity_to_return = 0
    new_product_stock = -1

    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Error de conexión a la base de datos.'}), 500

        # Cambia esta línea para usar dictionary=True para consistencia
        cursor = conn.cursor(dictionary=True) 
        conn.start_transaction()

        updated_cart = []
        item_found_in_cart = False

        current_cart = session.get('cart', [])
        for item in current_cart:
            if item['product_id'] == product_id_to_remove:
                quantity_to_return = item['quantity']
                item_found_in_cart = True
            else:
                updated_cart.append(item)

        if not item_found_in_cart:
            conn.rollback()
            return jsonify({'success': False, 'message': 'Producto no encontrado en el carrito de la sesión.'}), 404

        if quantity_to_return > 0:
            # Usa dictionary=True, así que accede por clave
            cursor.execute("SELECT stock FROM products WHERE id = %s FOR UPDATE", (product_id_to_remove,))
            product_db_info = cursor.fetchone()
            if not product_db_info:
                conn.rollback()
                return jsonify({'success': False, 'message': 'Producto no encontrado en la base de datos para reintegrar stock.'}), 404

            cursor.execute("UPDATE products SET stock = stock + %s WHERE id = %s",
                           (quantity_to_return, product_id_to_remove))
            print(f"DEBUG: Stock del producto ID {product_id_to_remove} incrementado en {quantity_to_return}.")

            # Usa dictionary=True, así que accede por clave
            cursor.execute("SELECT stock FROM products WHERE id = %s", (product_id_to_remove,))
            new_product_stock_info = cursor.fetchone()
            if new_product_stock_info:
                new_product_stock = new_product_stock_info['stock'] # Accede por la clave 'stock'

        session['cart'] = updated_cart
        session.modified = True

        conn.commit()

        cart_total = sum(item['product_price'] * item['quantity'] for item in session['cart'])

        flash('Producto eliminado del carrito y stock reintegrado.', 'success')
        return jsonify({
            'success': True,
            'message': 'Producto eliminado del carrito y stock reintegrado.',
            'cart': session['cart'],
            'cart_total': cart_total,
            'product_id': product_id_to_remove,
            'new_stock': new_product_stock
        })

    except Error as e:
        if conn:
            conn.rollback()
        print(f"Error al eliminar producto del carrito o reintegrar stock: {e}")
        flash(f"Error al eliminar del carrito: {e}", 'danger')
        return jsonify({'success': False, 'message': 'Error interno del servidor al eliminar del carrito.'}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

# --- RUTA PARA FINALIZAR LA VENTA ---
@app.route('/finalize_sale', methods=['POST'])
def finalize_sale():
    if not session.get('logged_in') or session.get('role') != 'employee':
        return jsonify({'success': False, 'message': 'Acceso denegado.'}), 401

    current_cart = session.get('cart', [])
    if not current_cart:
        return jsonify({'success': False, 'message': 'El carrito está vacío, no se puede finalizar la venta.'}), 400

    data = request.get_json()
    # Asegúrate de que client_id sea None si viene como string vacío o no está presente
    client_id = data.get('client_id')
    client_id_for_db = int(client_id) if client_id and client_id.strip() else None

    # --- INICIO DE LA MODIFICACIÓN ---
    # 1. Obtener el método de pago del JSON enviado desde el frontend
    payment_method = data.get('payment_method')

    # Opcional: Añadir una validación para asegurar que el método de pago no sea nulo
    if not payment_method:
        return jsonify({'success': False, 'message': 'Método de pago no proporcionado.'}), 400
    # --- FIN DE LA MODIFICACIÓN ---

    employee_id = session.get('user_id')
    if not employee_id:
        conn_fallback = get_db_connection()
        if conn_fallback:
            cursor_fallback = conn_fallback.cursor(dictionary=True)
            cursor_fallback.execute("SELECT id FROM users WHERE username = %s", (session.get('username'),))
            user_data = cursor_fallback.fetchone()
            if user_data:
                employee_id = user_data['id']
                session['user_id'] = employee_id
            cursor_fallback.close()
            conn_fallback.close()

        if not employee_id:
            return jsonify({'success': False, 'message': 'ID de empleado no disponible. Por favor, vuelve a iniciar sesión.'}), 500

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Error de conexión a la base de datos.'}), 500

        cursor = conn.cursor()
        conn.start_transaction()

        total_amount = sum(item['product_price'] * item['quantity'] for item in current_cart)

        # Insertar la venta
        # Asegurarse de que client_id es None si no se seleccionó, para la base de datos
        # --- INICIO DE LA MODIFICACIÓN ---
        # 2. Incluir 'payment_method' en la sentencia INSERT
        cursor.execute("INSERT INTO sales (sale_date, total_amount, employee_id, client_id, payment_method) VALUES (%s, %s, %s, %s, %s)",
                       (datetime.now(), total_amount, employee_id, client_id_for_db, payment_method))
        # --- FIN DE LA MODIFICACIÓN ---
        sale_id = cursor.lastrowid

        for item in current_cart:
            subtotal = item['product_price'] * item['quantity']
            cursor.execute(
                "INSERT INTO sale_details (sale_id, product_id, quantity, price_at_sale, subtotal) VALUES (%s, %s, %s, %s, %s)",
                (sale_id, item['product_id'], item['quantity'], item['product_price'], subtotal)
            )

        session['cart'] = []
        session.modified = True

        conn.commit()
        flash('Venta finalizada con éxito!', 'success')
        return jsonify({'success': True, 'message': 'Venta finalizada.', 'cart': [], 'cart_total': 0})

    except Error as e:
        if conn:
            conn.rollback()
        print(f"Error al finalizar la venta: {e}")
        flash(f"Error al finalizar la venta: {e}", 'danger')
        return jsonify({'success': False, 'message': 'Error interno del servidor al finalizar la venta.'}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


# --- RUTA PARA BUSCAR CLIENTES ---
@app.route('/clients/search', methods=['GET'])
def search_clients():
    """Busca clientes por nombre completo o DNI y devuelve los resultados en JSON."""
    if 'username' not in session or session.get('role') != 'employee':
        return jsonify({'success': False, 'message': 'Acceso denegado.'}), 401

    query = request.args.get('query', '').strip()
    clients = []
    conn = None
    cursor = None

    if len(query) < 2:
        return jsonify({'success': True, 'clients': []})

    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            search_pattern = f"%{query}%"
            cursor.execute("""
                SELECT id, full_name, dni, address, phone, email
                FROM clients
                WHERE full_name LIKE %s OR dni LIKE %s
                LIMIT 10
            """, (search_pattern, search_pattern))
            clients_data = cursor.fetchall()

            for client in clients_data:
                clients.append({
                    'id': client['id'],
                    'full_name': client['full_name'],
                    'dni': client['dni'] if client['dni'] else '',
                    'address': client['address'] if client['address'] else '',
                    'phone': client['phone'] if client['phone'] else '',
                    'email': client['email'] if client['email'] else ''
                })

    except Error as e:
        print(f"Error al buscar clientes: {e}")
        return jsonify({'success': False, 'message': 'Error al buscar clientes.'}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return jsonify({'success': True, 'clients': clients})

# --- RUTA PARA AÑADIR CLIENTE ---
@app.route('/employee/add_client', methods=['GET', 'POST'])
def add_client_view():
    # Solo permitir acceso a empleados/administradores si tienes roles
    # Ajusta los roles según cómo los tengas definidos en tu DB ('employee', 'admin')
    if 'user_id' not in session or session.get('role') not in ['employee', 'admin']:
        flash('Acceso denegado. Por favor, inicia sesión como empleado o administrador.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        full_name = request.form.get('full_name').strip()
        dni = request.form.get('dni').strip()
        address = request.form.get('address').strip()
        phone = request.form.get('phone').strip()
        email = request.form.get('email').strip()

        if not full_name:
            flash('El nombre completo es obligatorio.', 'danger')
            return render_template('add_cliente.html',
                                   full_name=full_name, dni=dni, address=address, phone=phone, email=email)

        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            if not conn:
                return render_template('add_cliente.html',
                                       full_name=full_name, dni=dni, address=address, phone=phone, email=email) # Error de conexión

            cursor = conn.cursor()
            conn.start_transaction()

            # 1. Verificar si el DNI ya existe (si DNI es único)
            if dni:
                cursor.execute("SELECT id FROM clients WHERE dni = %s", (dni,))
                existing_client = cursor.fetchone()
                if existing_client:
                    conn.rollback() # Deshacer la transacción
                    flash(f'Ya existe un cliente con el DNI/RUC {dni}.', 'danger')
                    return render_template('add_cliente.html',
                                           full_name=full_name, dni=dni, address=address, phone=phone, email=email)

            # 2. Insertar el nuevo cliente
            # Asegurarse de que los campos vacíos se inserten como NULL si la columna lo permite
            dni_for_db = dni if dni else None
            address_for_db = address if address else None
            phone_for_db = phone if phone else None
            email_for_db = email if email else None

            cursor.execute("""
                INSERT INTO clients (full_name, dni, address, phone, email)
                VALUES (%s, %s, %s, %s, %s)
            """, (full_name, dni_for_db, address_for_db, phone_for_db, email_for_db))

            conn.commit() # Confirmar los cambios
            flash('Cliente registrado exitosamente.', 'success')
            # Opción de redirección después de añadir:
            return redirect(url_for('new_sale_view')) # Redirige al punto de venta para que lo use inmediatamente
            # return redirect(url_for('add_client_view')) # Para añadir otro cliente

        except Error as e:
            if conn:
                conn.rollback() # En caso de error, deshacer
            flash(f'Error al registrar el cliente: {e}', 'danger')
            print(f"Error de base de datos al registrar cliente: {e}")
            return render_template('add_cliente.html',
                                   full_name=full_name, dni=dni, address=address, phone=phone, email=email)
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    return render_template('add_cliente.html',
                            full_name='', dni='', address='', phone='', email='') # Valores por defecto para GET


# --- RUTA PARA CONSULTAR VENTAS ---
@app.route('/employee/sales')
def consult_sales_view():
    """Permite a los empleados ver un historial de ventas, con opción de búsqueda."""
    user_id = session.get('user_id')
    user_role = session.get('role')

    if not user_id or user_role not in ['employee', 'admin']: # Añadí 'admin' aquí por si los admins también usan esta vista
        flash('Acceso denegado. No tienes permisos para ver ventas.', 'danger') # Mensaje más general
        return redirect(url_for('login_view')) # Corregido a 'login_view' si ese es el endpoint

    query = request.args.get('query', '').strip()
    sales_data = []

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)

            sql_query = """
                SELECT
                    s.id AS sale_id,
                    s.sale_date,
                    s.total_amount,
                    s.payment_method, -- <<<< AQUÍ ESTÁ LA LÍNEA CLAVE AÑADIDA
                    u.username AS employee_username,
                    u.first_name AS employee_first_name,
                    u.last_name AS employee_last_name,
                    c.full_name AS client_name,
                    c.dni AS client_dni,
                    c.address AS client_address,
                    c.phone AS client_phone,
                    c.email AS client_email,
                    sd.product_id,
                    p.name AS product_name,
                    sd.quantity,
                    sd.price_at_sale,
                    sd.subtotal
                FROM
                    sales s
                JOIN
                    users u ON s.employee_id = u.id
                LEFT JOIN
                    clients c ON s.client_id = c.id
                LEFT JOIN
                    sale_details sd ON s.id = sd.sale_id
                LEFT JOIN
                    products p ON sd.product_id = p.id
            """
            params = []

            if query:
                where_clauses = []
                try:
                    query_as_int = int(query)
                    # Usamos `OR` para buscar por ID de venta si es un número válido
                    where_clauses.append("s.id = %s")
                    params.append(query_as_int)
                except ValueError:
                    # Si no es un número, entonces es un patrón de texto para nombres/DNI
                    pass
                
                search_pattern = f"%{query}%"
                where_clauses.append("c.full_name LIKE %s")
                params.append(search_pattern)
                where_clauses.append("u.username LIKE %s")
                params.append(search_pattern)
                where_clauses.append("u.first_name LIKE %s")
                params.append(search_pattern)
                where_clauses.append("u.last_name LIKE %s")
                params.append(search_pattern)
                where_clauses.append("c.dni LIKE %s") # Añadir búsqueda por DNI del cliente
                params.append(search_pattern)

                if where_clauses:
                    sql_query += " WHERE (" + " OR ".join(where_clauses) + ")"

            sql_query += " ORDER BY s.sale_date DESC, s.id, p.name"

            print(f"--- Depuración de consult_sales_view ---")
            print(f"SQL a ejecutar:\n{sql_query}")
            print(f"Parámetros: {params}")

            cursor.execute(sql_query, tuple(params))
            raw_sales = cursor.fetchall()

            print(f"Número de filas obtenidas de la DB: {len(raw_sales)}")
            print(f"Contenido de raw_sales (desde DB, primeros 5 rows): {raw_sales[:5]} {'...' if len(raw_sales) > 5 else ''}")

            grouped_sales = {}
            for row in raw_sales:
                sale_id = row['sale_id']
                if sale_id not in grouped_sales:
                    grouped_sales[sale_id] = {
                        'sale_id': row['sale_id'],
                        'sale_date': row['sale_date'],
                        'total_amount': float(row['total_amount']),
                        'payment_method': row['payment_method'], # <<<< ASEGÚRATE DE QUE ESTA LÍNEA ESTÉ AQUÍ
                        'employee_username': row['employee_username'],
                        'employee_first_name': row['employee_first_name'],
                        'employee_last_name': row['employee_last_name'],
                        'client_name': row['client_name'] if row['client_name'] is not None else 'N/A',
                        'client_dni': row['client_dni'] if row['client_dni'] is not None else 'N/A',
                        'client_address': row['client_address'] if row['client_address'] is not None else 'N/A',
                        'client_phone': row['client_phone'] if row['client_phone'] is not None else 'N/A',
                        'client_email': row['client_email'] if row['client_email'] is not None else 'N/A',
                        'items': [] 
                    }
                
                if row['product_id'] is not None:
                    grouped_sales[sale_id]['items'].append({
                        'product_id': row['product_id'],
                        'product_name': row['product_name'],
                        'quantity': row['quantity'],
                        'price_at_sale': float(row['price_at_sale']),
                        'subtotal': float(row['subtotal'])
                    })

            sales_data = list(grouped_sales.values())
            sales_data.sort(key=lambda x: x['sale_date'], reverse=True)
            
            # --- MEDIDA DEFENSIVA ADICIONAL ---
            for sale in sales_data:
                if 'items' not in sale or not isinstance(sale['items'], list):
                    sale['items'] = [] # Asegura que siempre sea una lista
            # --- FIN MEDIDA DEFENSIVA ---

            print(f"Número de ventas agrupadas para renderizar: {len(sales_data)}")
            print(f"Contenido de sales_data (final para HTML, primeros 2 ventas): {sales_data[:2]} {'...' if len(sales_data) > 2 else ''}") 
            print("-------------------------------------")

    except Error as e:
        flash(f"Error al cargar las ventas desde la base de datos: {e}", 'danger')
        print(f"ERROR: Fallo en la base de datos para consultar ventas: {e}")
        sales_data = []
    except Exception as e:
        flash(f"Error inesperado al cargar las ventas: {e}", 'danger')
        print(f"ERROR: Fallo inesperado en Python al consultar ventas: {e}")
        sales_data = []
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
            print("Conexión a DB cerrada para consulta de ventas.")
    
    return render_template('consult_sales.html',
                           full_name=session.get('full_name', session.get('username', 'Empleado')),
                           sales=sales_data)



# --- RUTA PARA GENERAR LA BOLETA DE VENTA ---
@app.route('/invoice/<int:sale_id>')
def generate_invoice(sale_id):
    """
    Genera la boleta de venta para un sale_id específico.
    Puede ser accedida por empleados o administradores.
    Acepta un parámetro 'origin' en la URL para determinar la URL de retorno.
    """
    # Obtener el parámetro 'origin' de la URL, por defecto None si no se proporciona
    origin = request.args.get('origin')

    user_id = session.get('user_id')
    user_role = session.get('role')

    if not user_id or user_role not in ['employee', 'admin']:
        flash('Acceso denegado. Por favor, inicia sesión con los permisos adecuados.', 'danger')
        return redirect(url_for('login_view'))

    conn = None
    cursor = None
    invoice_data = None 

    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)

            sql_sale_info = """
                SELECT
                    s.id AS sale_id,
                    s.sale_date,
                    s.total_amount,
                    s.payment_method,
                    s.is_cancelled,
                    s.employee_id,
                    u.username AS employee_username,
                    u.first_name AS employee_first_name,
                    u.last_name AS employee_last_name,
                    c.full_name AS client_name,
                    c.dni AS client_dni,
                    c.address AS client_address,
                    c.phone AS client_phone,
                    c.email AS client_email
                FROM
                    sales s
                JOIN
                    users u ON s.employee_id = u.id
                LEFT JOIN
                    clients c ON s.client_id = c.id
                WHERE
                    s.id = %s
            """
            params = [sale_id]

            # Si el usuario NO es un administrador, añadir la restricción para que solo vea sus propias ventas
            if user_role != 'admin':
                sql_sale_info += " AND s.employee_id = %s"
                params.append(user_id)

            cursor.execute(sql_sale_info, tuple(params))
            invoice_data = cursor.fetchone()

            if not invoice_data:
                flash(f'Boleta con ID {sale_id} no encontrada o no tienes permiso para verla.', 'danger')
                if user_role == 'admin':
                    return redirect(url_for('admin_boletas_reports_view'))
                else:
                    return redirect(url_for('consult_sales_view'))

            # Procesar la fecha de la venta
            processed_sale_date = invoice_data['sale_date']
            if isinstance(processed_sale_date, str):
                try:
                    processed_sale_date = datetime.strptime(processed_sale_date, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    try:
                        processed_sale_date = datetime.strptime(processed_sale_date, '%Y-%m-%d')
                    except ValueError:
                        print(f"Advertencia: sale_date '{invoice_data['sale_date']}' no se pudo parsear. Dejando como cadena.")
                        pass
            invoice_data['sale_date_formatted'] = processed_sale_date.strftime('%d/%m/%Y %H:%M:%S') if isinstance(processed_sale_date, (datetime, date)) else str(processed_sale_date)


            # Obtener los detalles de los productos de la venta
            sql_sale_details = """
                SELECT
                    sd.product_id,
                    p.name AS product_name,
                    sd.quantity,
                    sd.price_at_sale,
                    sd.subtotal
                FROM
                    sale_details sd
                JOIN
                    products p ON sd.product_id = p.id
                WHERE
                    sd.sale_id = %s
                ORDER BY
                    p.name ASC
            """
            cursor.execute(sql_sale_details, (sale_id,))
            sale_items = cursor.fetchall()
            
            invoice_data['items'] = []
            for item in sale_items:
                invoice_data['items'].append({
                    'product_id': item['product_id'],
                    'product_name': item['product_name'],
                    'quantity': item['quantity'],
                    'price_at_sale': float(item['price_at_sale']),
                    'subtotal': float(item['subtotal'])
                })

            # Cálculos de subtotal, IGV y total final
            subtotal_calculated = sum(item['subtotal'] for item in invoice_data['items'])
            igv_rate = 0.18
            igv_calculated = subtotal_calculated * igv_rate
            total_final = subtotal_calculated + igv_calculated

            # --- ¡¡¡NUEVA LÍNEA PARA LA FECHA DE EMISIÓN!!! ---
            current_emission_date = datetime.now().strftime('%d/%m/%Y %H:%M:%S')

            # Depuración: Imprime lo que se enviará a la plantilla
            print(f"--- Datos de la Boleta para renderizar (sale_id: {sale_id}) ---")
            print(invoice_data)
            print(f"Subtotal calculado: {subtotal_calculated}, IGV calculado: {igv_calculated}, Total final: {total_final}")
            print(f"Fecha de Emisión (calculada en Python): {current_emission_date}")
            print("-------------------------------------")

            return render_template('invoice_template.html',
                                   invoice=invoice_data,
                                   subtotal_calculated=round(subtotal_calculated, 2),
                                   igv_calculated=round(igv_calculated, 2),
                                   total_calculated=round(total_final, 2),
                                   company_name="Tu Empresa S.A.C.",
                                   company_address="Av. Principal 123, Ciudad",
                                   company_phone="+51 987 654 321",
                                   company_ruc="20123456789",
                                   origin=origin,
                                   emission_date=current_emission_date # <-- ¡PASAMOS LA NUEVA VARIABLE AQUÍ!
                                   )

    except Error as e:
        flash(f"Error de base de datos al generar la boleta: {e}", 'danger')
        print(f"ERROR: Fallo en la base de datos para boleta: {e}")
        if user_role == 'admin':
            return redirect(url_for('admin_boletas_reports_view'))
        else:
            return redirect(url_for('consult_sales_view'))
    except Exception as e:
        flash(f"Error inesperado al generar la boleta: {e}", 'danger')
        print(f"ERROR: Fallo inesperado en Python para boleta: {e}")
        if user_role == 'admin':
            return redirect(url_for('admin_boletas_reports_view'))
        else:
            return redirect(url_for('consult_sales_view'))

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
            print("Conexión a DB cerrada para boleta.")


# --- FILTRO DE FECHA Y HORA ---
@app.template_filter('datetimeformat')
def datetimeformat(value, format='%d/%m/%Y %H:%M'): # Usamos el formato de tu plantilla por defecto
    if value is None:
        return ""
    if isinstance(value, datetime): # Si ya es un objeto datetime, formatéalo directamente
        return value.strftime(format)
    else:
        try:
            # Intenta parsear la cadena (quitando microsegundos si existen)
            dt_object = datetime.strptime(str(value).split('.')[0], '%Y-%m-%d %H:%M:%S')
            return dt_object.strftime(format)
        except (ValueError, TypeError):
            # Si no se puede convertir a datetime, devuelve el valor original como string
            return str(value) if value is not None else ""


# --- RUTA PARA CONSULTAR CLIENTES ---
@app.route('/clients/consult')
def consult_clients_view():
    """Página para consultar clientes (accesible por empleados y administradores)."""
    if not session.get('logged_in') or session.get('role') not in ['employee', 'admin']:
        flash('Acceso denegado. Por favor, inicia sesión con los permisos adecuados.', 'danger')
        return redirect(url_for('login'))

    conn = None
    cursor = None
    clients = []
    search_query = request.args.get('query', '') # Obtener el término de búsqueda

    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)

            # Consulta base para todos los clientes
            sql_query = "SELECT id, full_name, dni, address, phone, email FROM clients"
            params = []

            # Si hay un término de búsqueda, añadir la cláusula WHERE
            if search_query:
                sql_query += " WHERE full_name LIKE %s OR dni LIKE %s OR phone LIKE %s OR email LIKE %s"
                # Añadir % a los términos de búsqueda para buscar coincidencias parciales
                search_term = f"%{search_query}%"
                params = [search_term, search_term, search_term, search_term]
            
            # --- CAMBIO AQUÍ: Ordenar por ID ASCENDENTE ---
            sql_query += " ORDER BY id ASC" 

            cursor.execute(sql_query, params)
            clients = cursor.fetchall()

    except Error as e:
        flash(f"Error de base de datos al consultar clientes: {e}", 'danger')
        print(f"ERROR: Fallo en la base de datos al consultar clientes: {e}")
    except Exception as e:
        flash(f"Error inesperado al consultar clientes: {e}", 'danger')
        print(f"ERROR: Fallo inesperado en Python al consultar clientes: {e}")
        # Considera quitar 'raise e' en producción, pero es útil para depuración
        raise e 
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
            print("Conexión a DB cerrada para consulta de clientes.")

    return render_template('consult_clients.html',
                           full_name=session.get('full_name', session['username']),
                           clients=clients,
                           search_query=search_query)


# --- NUEVA RUTA PARA OBTENER DETALLES DE UN CLIENTE (PARA EL MODAL DE EDICIÓN) ---
@app.route('/client_details/<int:client_id>')
def get_client_details(client_id):
    if not session.get('logged_in') or session.get('role') not in ['employee', 'admin']:
        return jsonify({'success': False, 'message': 'Acceso denegado.'}), 403

    conn = None
    cursor = None
    client_data = None
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, full_name, dni, address, phone, email FROM clients WHERE id = %s", (client_id,))
            client_data = cursor.fetchone()

            if client_data:
                return jsonify({'success': True, 'client': client_data})
            else:
                return jsonify({'success': False, 'message': 'Cliente no encontrado.'}), 404
    except Error as e:
        print(f"ERROR: Fallo en la base de datos al obtener detalles del cliente: {e}")
        return jsonify({'success': False, 'message': f'Error de base de datos: {e}'}), 500
    except Exception as e:
        print(f"ERROR: Fallo inesperado al obtener detalles del cliente: {e}")
        return jsonify({'success': False, 'message': f'Error inesperado: {e}'}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
            print("Conexión a DB cerrada para detalles de cliente.")


# --- NUEVA RUTA PARA ACTUALIZAR CLIENTE (RECIBE DATOS DEL MODAL) ---
@app.route('/clients/update/<int:client_id>', methods=['POST'])
def update_client(client_id):
    if not session.get('logged_in') or session.get('role') not in ['employee', 'admin']:
        return jsonify({'success': False, 'message': 'Acceso denegado.'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'No se recibieron datos.'}), 400

    address = data.get('address')
    phone = data.get('phone')
    email = data.get('email')

    if not all([address, phone, email]):
        return jsonify({'success': False, 'message': 'Todos los campos (Dirección, Teléfono, Email) son requeridos.'}), 400
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE clients SET address = %s, phone = %s, email = %s WHERE id = %s",
                (address, phone, email, client_id)
            )
            conn.commit()
            if cursor.rowcount > 0:
                flash('Cliente actualizado exitosamente.', 'success')
                return jsonify({'success': True, 'message': 'Cliente actualizado exitosamente.'})
            else:
                flash('No se encontró el cliente o no hubo cambios para actualizar.', 'info')
                return jsonify({'success': False, 'message': 'No se encontró el cliente o no hubo cambios para actualizar.'}), 404
    except Error as e:
        flash(f"Error de base de datos al actualizar cliente: {e}", 'danger')
        print(f"ERROR: Fallo en la base de datos al actualizar cliente: {e}")
        return jsonify({'success': False, 'message': f'Error de base de datos: {e}'}), 500
    except Exception as e:
        flash(f"Error inesperado al actualizar cliente: {e}", 'danger')
        print(f"ERROR: Fallo inesperado al actualizar cliente: {e}")
        return jsonify({'success': False, 'message': f'Error inesperado: {e}'}), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
            print("Conexión a DB cerrada para actualización de cliente.")

# RUTA PARA ELIMINAR CLIENTE
@app.route('/clients/delete/<int:client_id>', methods=['POST'])
def delete_client(client_id):
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Error de conexión a la base de datos.'}), 500

        cursor = conn.cursor()
        
        # Opcional pero recomendado: Verificar si el cliente existe antes de intentar eliminar
        cursor.execute("SELECT id FROM clients WHERE id = %s", (client_id,))
        client_exists = cursor.fetchone()
        if not client_exists:
            conn.close()
            return jsonify({'success': False, 'message': 'Cliente no encontrado.'}), 404

        # Realizar la eliminación
        cursor.execute("DELETE FROM clients WHERE id = %s", (client_id,))
        conn.commit() # Confirmar los cambios en la base de datos
        conn.close()

        if cursor.rowcount > 0: # rowcount > 0 significa que se eliminó al menos una fila
            return jsonify({'success': True, 'message': 'Cliente eliminado exitosamente.'})
        else:
            # Esto no debería ocurrir si el check de client_exists pasó
            return jsonify({'success': False, 'message': 'No se pudo eliminar el cliente (posiblemente ya no exista).'}), 500

    except mysql.connector.Error as err:
        print(f"Error al eliminar cliente (DB): {err}")
        if conn:
            conn.rollback() # Deshacer cambios si hay un error
        return jsonify({'success': False, 'message': f'Error en la base de datos al eliminar cliente: {str(err)}'}), 500
    except Exception as e:
        print(f"Error inesperado al eliminar cliente: {e}")
        if conn:
            conn.rollback() # Deshacer cambios si hay un error
        return jsonify({'success': False, 'message': f'Error interno del servidor: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()

# RUTA PARA VER PERFIL DEL USUARIO EMPLEADO
@app.route('/my_profile')
def my_profile_view():
    conn = None
    try:
        user_id = session.get('user_id')
        user_role = session.get('role')

        print(f"DEBUG: En /my_profile - user_id de sesión: {user_id}")
        print(f"DEBUG: En /my_profile - user_role de sesión: {user_role}")

        # --- VERIFICACIÓN DE LOGUEO ---
        if not user_id:
            flash('Debes iniciar sesión para ver tu perfil.', 'warning')
            print("DEBUG: Redirigiendo a login_view - user_id no encontrado.")
            return redirect(url_for('login_view')) 
        
        # --- VERIFICACIÓN DE ROL ---
        if user_role != 'employee':
            flash('Acceso denegado. Solo los empleados pueden ver esta página.', 'danger')
            print(f"DEBUG: Acceso denegado - Rol '{user_role}' no es 'employee'. Redirigiendo a employee_dashboard_view.")
            return redirect(url_for('employee_dashboard_view'))

        # --- CONEXIÓN A LA BASE DE DATOS Y CONSULTA ---
        conn = get_db_connection()
        if not conn:
            flash('Error de conexión a la base de datos.', 'danger')
            print("DEBUG: Error: No se pudo establecer conexión con la base de datos.")
            return redirect(url_for('employee_dashboard_view')) 

        cursor = conn.cursor(dictionary=True) 
        print(f"DEBUG: Ejecutando consulta SQL para user_id: {user_id} (con phone, address, email, DNI)")
        cursor.execute("SELECT id, username, first_name, last_name, phone, address, email, dni, role FROM users WHERE id = %s", (user_id,))
        user_info = cursor.fetchone()
        
        conn.close()

        print(f"DEBUG: Resultado de la consulta user_info: {user_info}")

        if user_info:
            print("DEBUG: user_info encontrado. Renderizando my_profile.html.")
            return render_template('my_profile.html', user_info=user_info)
        else:
            flash('No se encontró información para el usuario logueado en la base de datos.', 'warning')
            print(f"DEBUG: Error: user_info es None para user_id: {user_id}. Redirigiendo a employee_dashboard_view.")
            return redirect(url_for('employee_dashboard_view')) 

    except mysql.connector.Error as err:
        print(f"ERROR DE BD: {err}")
        flash(f'Error de base de datos al cargar perfil: {str(err)}', 'danger')
        return redirect(url_for('employee_dashboard_view'))
    except Exception as e:
        print(f"ERROR INESPERADO: {e}")
        flash(f'Error inesperado al cargar perfil: {str(e)}', 'danger')
        return redirect(url_for('employee_dashboard_view'))
    finally:
        if conn:
            conn.close()

@app.route('/update_my_profile', methods=['POST'])
def update_my_profile():
    conn = None
    try:
        user_id = session.get('user_id')
        user_role = session.get('role')

        if not user_id:
            return jsonify({'success': False, 'message': 'Usuario no autenticado.'}), 401
        
        if user_role not in ['employee', 'admin']: # Ajusta si solo empleados pueden editar su perfil
            return jsonify({'success': False, 'message': 'Acceso denegado. No tienes permisos para editar este perfil.'}), 403

        # Obtener los datos del formulario (enviados como FormData)
        phone = request.form.get('phone')
        address = request.form.get('address')
        email = request.form.get('email')
        # user_id del formulario es para verificación, pero usamos el de la sesión para seguridad
        user_id_from_form = request.form.get('user_id')

        # Pequeña validación de seguridad: Asegurarse de que el ID en el formulario coincide con el de la sesión
        if str(user_id) != user_id_from_form:
            return jsonify({'success': False, 'message': 'Error de seguridad: ID de usuario no coincide.'}), 403

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Error de conexión a la base de datos.'}), 500

        cursor = conn.cursor()
        
        # Actualizar solo los campos que se permiten editar (teléfono, dirección, email)
        # Puedes añadir más campos aquí si necesitas que sean editables.
        update_query = """
            UPDATE users 
            SET phone = %s, address = %s, email = %s 
            WHERE id = %s
        """
        cursor.execute(update_query, (phone, address, email, user_id))
        conn.commit() # Confirmar los cambios en la base de datos
        
        # Opcional: Obtener la información actualizada para devolverla
        # Esto es útil para que el frontend pueda actualizar sin recargar
        cursor.execute("SELECT phone, address, email FROM users WHERE id = %s", (user_id,))
        updated_info = cursor.fetchone() # Usamos fetchone() porque es un solo usuario

        return jsonify({
            'success': True, 
            'message': 'Perfil actualizado exitosamente.',
            'updated_info': {
                'phone': updated_info[0] if updated_info else phone, # Asumiendo que updated_info es una tupla
                'address': updated_info[1] if updated_info else address,
                'email': updated_info[2] if updated_info else email
            }
        }), 200

    except mysql.connector.Error as err:
        print(f"ERROR DE BD al actualizar perfil: {err}")
        return jsonify({'success': False, 'message': f'Error de base de datos: {str(err)}'}), 500
    except Exception as e:
        print(f"ERROR INESPERADO al actualizar perfil: {e}")
        return jsonify({'success': False, 'message': f'Error inesperado: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()


# RUTA PARA MOSTRAR EL FORMULARIO DE CAMBIO DE CONTRASEÑA
@app.route('/change_password', methods=['GET'])
def change_password_view():
    conn = None
    try:
        user_id = session.get('user_id')
        user_role = session.get('role')

        if not user_id:
            flash('Debes iniciar sesión para cambiar tu contraseña.', 'warning')
            return redirect(url_for('login_view'))
        
        if user_role not in ['employee', 'admin']: # Ajusta según tus roles
            flash('Acceso denegado. No tienes permisos para cambiar la contraseña.', 'danger')
            return redirect(url_for('employee_dashboard_view')) # Redirige a donde sea apropiado

        conn = get_db_connection()
        if not conn:
            flash('Error de conexión a la base de datos.', 'danger')
            return redirect(url_for('employee_dashboard_view'))

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, username, first_name, last_name FROM users WHERE id = %s", (user_id,))
        user_info = cursor.fetchone()
        
        if not user_info:
            flash('No se encontró información del usuario.', 'danger')
            return redirect(url_for('employee_dashboard_view'))

        return render_template('change_password.html', user_info=user_info)

    except mysql.connector.Error as err:
        print(f"ERROR DE BD al cargar formulario de contraseña: {err}")
        flash(f'Error de base de datos: {str(err)}', 'danger')
        return redirect(url_for('employee_dashboard_view'))
    except Exception as e:
        print(f"ERROR INESPERADO al cargar formulario de contraseña: {e}")
        flash(f'Error inesperado: {str(e)}', 'danger')
        return redirect(url_for('employee_dashboard_view'))
    finally:
        if conn:
            conn.close()

# RUTA PARA PROCESAR EL CAMBIO DE CONTRASEÑA (POST) - SIN HASHING
@app.route('/update_password', methods=['POST'])
def update_password():
    conn = None
    try:
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({'success': False, 'message': 'Usuario no autenticado.'}), 401

        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_new_password = request.form.get('confirm_new_password')

        # --- Validaciones de campos ---
        if not all([current_password, new_password, confirm_new_password]):
            return jsonify({'success': False, 'message': 'Todos los campos son requeridos.'}), 400

        if new_password != confirm_new_password:
            return jsonify({'success': False, 'message': 'La nueva contraseña y su confirmación no coinciden.'}), 400
        
        if len(new_password) < 6: # Ejemplo: mínimo 6 caracteres
            return jsonify({'success': False, 'message': 'La nueva contraseña debe tener al menos 6 caracteres.'}), 400
        
        # Opcional: Evitar que la nueva contraseña sea igual a la actual
        if new_password == current_password:
             return jsonify({'success': False, 'message': 'La nueva contraseña no puede ser igual a la actual.'}), 400


        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Error de conexión a la base de datos.'}), 500

        cursor = conn.cursor(dictionary=True)
        # Obtener la contraseña actual de la DB (¡EN TEXTO PLANO!)
        cursor.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()

        # Comparar la contraseña actual proporcionada con la almacenada (¡EN TEXTO PLANO!)
        if not user_data or user_data['password_hash'] != current_password:
            return jsonify({'success': False, 'message': 'Contraseña actual incorrecta.'}), 400

        # Si la contraseña actual es correcta, actualizar con la nueva contraseña (¡EN TEXTO PLANO!)
        cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_password, user_id))
        conn.commit()

        return jsonify({'success': True, 'message': 'Contraseña actualizada exitosamente.'}), 200

    except mysql.connector.Error as err:
        print(f"ERROR DE BD al actualizar contraseña: {err}")
        return jsonify({'success': False, 'message': f'Error de base de datos: {str(err)}'}), 500
    except Exception as e:
        print(f"ERROR INESPERADO al actualizar contraseña: {e}")
        return jsonify({'success': False, 'message': f'Error inesperado: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()


# --------------------------------------------------------
# RUTAS PARA EL DASHBOARD DEL ADMINISTRADOR
# --------------------------------------------------------

# --- Rutas del Dashboard de Administrador ---
@app.route('/admin_dashboard')
def admin_dashboard_view():
    user_id = session.get('user_id')
    user_role = session.get('role')

    # 1. Verificar autenticación y rol de administrador
    if not user_id or user_role != 'admin':
        flash('Acceso denegado. Solo los administradores pueden acceder a este panel.', 'danger')
        return redirect(url_for('login_view'))

    conn = None
    full_name = "Administrador" # Valor por defecto

    stats = {
        'total_sales_today': 0.0,
        'num_employees': 0,
        'num_clients': 0,
        'total_products_in_stock': 0,
        'low_stock_products_count': 0,
        'low_stock_products_list': [],
        'total_products_count': 0,
        'sales_history': {'labels': [], 'values': []},
        'top_selling_products': [], # Se llenará con los 5 productos más vendidos para el gráfico
        'top_employee_sales': {'name': 'N/A', 'total_sales': 0.0}, # Ventas HOY
        'top_employee_sales_week': {'name': 'N/A', 'total_sales': 0.0}, # Ventas SEMANA
        'top_employee_sales_month': {'name': 'N/A', 'total_sales': 0.0}, # Ventas MES
        'top_employee_by_product': [], # Para la estadística por producto
        'employee_sales_chart': {'labels': [], 'data': []} # Para el gráfico de barras por empleado
    }

    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)

            # Obtener el nombre completo del administrador desde la DB
            cursor.execute("SELECT first_name, last_name, username FROM users WHERE id = %s", (user_id,))
            user_data = cursor.fetchone()
            if user_data:
                if user_data.get('first_name') and user_data.get('last_name'):
                    full_name = f"{user_data['first_name']} {user_data['last_name']}"
                else: # Si no tiene first_name/last_name, usa el username
                    full_name = user_data['username']

            # --- Estadísticas del Resumen del Sistema ---
            
            # Total de ventas de hoy
            today = date.today()
            cursor.execute("SELECT SUM(total_amount) AS total FROM sales WHERE DATE(sale_date) = %s", (today,))
            sales_data = cursor.fetchone()
            if sales_data and sales_data['total'] is not None:
                stats['total_sales_today'] = round(float(sales_data['total']), 2)

            # Número de empleados (usuarios con role='employee')
            cursor.execute("SELECT COUNT(id) AS count FROM users WHERE role = 'employee'")
            employees_data = cursor.fetchone()
            if employees_data and employees_data['count'] is not None:
                stats['num_employees'] = employees_data['count']

            # Número de clientes (asumiendo que tienes una tabla 'clients')
            cursor.execute("SELECT COUNT(id) AS count FROM clients")
            clients_data = cursor.fetchone()
            if clients_data and clients_data['count'] is not None:
                stats['num_clients'] = clients_data['count']

            # Stock total de productos (suma de la columna 'stock' en la tabla 'products')
            cursor.execute("SELECT SUM(stock) AS total_stock FROM products")
            stock_data = cursor.fetchone()
            if stock_data and stock_data['total_stock'] is not None:
                stats['total_products_in_stock'] = int(stock_data['total_stock']) # Asegurarse de que es entero

            # Productos con bajo stock (stock < 25 como solicitaste)
            LOW_STOCK_THRESHOLD = 25 # Define el límite aquí
            cursor.execute("SELECT name, stock FROM products WHERE stock <= %s ORDER BY stock ASC", (LOW_STOCK_THRESHOLD,))
            low_stock_products = cursor.fetchall()
            stats['low_stock_products_count'] = len(low_stock_products)
            # Limita la lista a mostrar, por ejemplo, los primeros 10-15 para evitar una lista excesivamente larga
            stats['low_stock_products_list'] = low_stock_products[:15] # Muestra solo los primeros 15

            # Total de productos registrados (conteo total de filas en la tabla 'products')
            cursor.execute("SELECT COUNT(id) AS count FROM products")
            total_products_data = cursor.fetchone()
            if total_products_data and total_products_data['count'] is not None:
                stats['total_products_count'] = total_products_data['count']

            # --- Consultas para los Gráficos y TOP Empleados ---

            # Historial de ventas (últimos 7 días) para el gráfico de línea
            sales_labels = []
            sales_values = []
            num_days_history = 7

            for i in range(num_days_history - 1, -1, -1): # Desde 6 días atrás hasta hoy
                current_date = today - timedelta(days=i)
                sales_labels.append(current_date.strftime("%d/%b")) # Formato "DD/MesAbrev"

                cursor.execute("SELECT SUM(total_amount) AS total FROM sales WHERE DATE(sale_date) = %s", (current_date,))
                daily_sales_data = cursor.fetchone()
                if daily_sales_data and daily_sales_data['total'] is not None:
                    sales_values.append(round(float(daily_sales_data['total']), 2))
                else:
                    sales_values.append(0.0)

            stats['sales_history']['labels'] = sales_labels
            stats['sales_history']['values'] = sales_values

            # Productos más vendidos (Top 5) - Utilizado para el gráfico de pastel y para la sección de "empleado por producto"
            cursor.execute("""
                SELECT
                    p.id AS product_id,
                    p.name AS product_name,
                    SUM(sd.quantity) AS total_sold
                FROM sale_details sd
                JOIN products p ON sd.product_id = p.id
                GROUP BY p.id, p.name
                ORDER BY total_sold DESC
                LIMIT 5
            """)
            top_selling_products_raw = cursor.fetchall()
            stats['top_selling_products'] = top_selling_products_raw # Asigna esto para el gráfico de pastel

            # Para cada producto top, encontrar al empleado que más lo vendió
            # (Solo si hay productos top vendidos)
            if top_selling_products_raw:
                for product in top_selling_products_raw:
                    product_id = product['product_id']
                    product_name = product['product_name']
                    total_sold_product = product['total_sold'] # Total vendido de este producto

                    cursor.execute("""
                        SELECT
                            u.first_name,
                            u.last_name,
                            u.username,
                            SUM(sd.quantity) AS quantity_sold_by_employee
                        FROM sales s
                        JOIN sale_details sd ON s.id = sd.sale_id
                        JOIN users u ON s.employee_id = u.id -- IMPORTANTE: Usar employee_id para ventas de empleados
                        WHERE sd.product_id = %s AND u.role = 'employee'
                        GROUP BY u.id, u.first_name, u.last_name, u.username
                        ORDER BY quantity_sold_by_employee DESC
                        LIMIT 1
                    """, (product_id,))
                    top_employee_for_product = cursor.fetchone()

                    employee_info = {
                        'name': 'N/A',
                        'quantity_sold': 0
                    }
                    if top_employee_for_product:
                        # Prioriza first_name + last_name, luego username
                        if top_employee_for_product.get('first_name') and top_employee_for_product.get('last_name'):
                            employee_info['name'] = f"{top_employee_for_product['first_name']} {top_employee_for_product['last_name']}"
                        elif top_employee_for_product.get('username'):
                            employee_info['name'] = top_employee_for_product['username']
                        employee_info['quantity_sold'] = int(top_employee_for_product['quantity_sold_by_employee'])

                    stats['top_employee_by_product'].append({
                        'product_name': product_name,
                        'total_sold_product': int(total_sold_product),
                        'top_employee': employee_info
                    })

            # --- Función auxiliar para obtener el empleado con más ventas en un período ---
            def get_top_employee_sales(cursor, start_date, end_date=None):
                query = """
                    SELECT
                        u.first_name,
                        u.last_name,
                        u.username,
                        SUM(s.total_amount) AS total_sales_by_employee
                    FROM sales s
                    JOIN users u ON s.employee_id = u.id -- Asegúrate de que esta columna es correcta (employee_id)
                    WHERE u.role = 'employee'
                """
                params = []
                if end_date: # Rango de fechas
                    query += " AND s.sale_date BETWEEN %s AND %s"
                    params.extend([start_date, end_date])
                else: # Fecha específica (hoy)
                    query += " AND DATE(s.sale_date) = %s"
                    params.append(start_date)

                query += """
                    GROUP BY u.id, u.first_name, u.last_name, u.username
                    ORDER BY total_sales_by_employee DESC
                    LIMIT 1
                """
                cursor.execute(query, tuple(params))
                employee_data = cursor.fetchone()
                
                result = {'name': 'N/A', 'total_sales': 0.0}
                if employee_data:
                    if employee_data.get('first_name') and employee_data.get('last_name'):
                        result['name'] = f"{employee_data['first_name']} {employee_data['last_name']}"
                    elif employee_data.get('username'):
                        result['name'] = employee_data['username'] # Fallback
                    result['total_sales'] = round(float(employee_data['total_sales_by_employee']), 2)
                return result

            # Empleado con más ventas HOY
            stats['top_employee_sales'] = get_top_employee_sales(cursor, today)
            if stats['top_employee_sales']['name'] == 'N/A':
                stats['top_employee_sales']['name'] = 'Nadie ha vendido aún hoy'

            # Empleado con más ventas SEMANAL
            start_of_week = today - timedelta(days=today.weekday()) # Lunes de la semana actual
            end_of_week = start_of_week + timedelta(days=6) # Domingo de la semana actual
            stats['top_employee_sales_week'] = get_top_employee_sales(cursor, start_of_week, end_of_week)
            if stats['top_employee_sales_week']['name'] == 'N/A':
                stats['top_employee_sales_week']['name'] = 'Nadie ha vendido aún esta semana'

            # Empleado con más ventas MENSUAL
            start_of_month = date(today.year, today.month, 1) # Primer día del mes actual
            stats['top_employee_sales_month'] = get_top_employee_sales(cursor, start_of_month, today)
            if stats['top_employee_sales_month']['name'] == 'N/A':
                stats['top_employee_sales_month']['name'] = 'Nadie ha vendido aún este mes'
            
            # --- Obtener ventas por empleado para el gráfico de barras (todos los empleados) ---
            cursor.execute("""
                SELECT
                    u.first_name,
                    u.last_name,
                    u.username,
                    SUM(s.total_amount) AS total_sales_by_employee
                FROM sales s
                JOIN users u ON s.employee_id = u.id -- Asegúrate de que esta columna es correcta
                WHERE u.role = 'employee'
                GROUP BY u.id, u.first_name, u.last_name, u.username
                ORDER BY total_sales_by_employee DESC
            """)
            employee_sales_raw = cursor.fetchall()

            employee_chart_labels = []
            employee_chart_data = []

            for employee_sale in employee_sales_raw:
                employee_name = ""
                if employee_sale.get('first_name') and employee_sale.get('last_name'):
                    employee_name = f"{employee_sale['first_name']} {employee_sale['last_name']}"
                elif employee_sale.get('username'):
                    employee_name = employee_sale['username']
                else:
                    employee_name = "Empleado Desconocido" # Fallback si no hay nombre ni username

                employee_chart_labels.append(employee_name)
                employee_chart_data.append(round(float(employee_sale['total_sales_by_employee']), 2))
            
            stats['employee_sales_chart']['labels'] = employee_chart_labels
            stats['employee_sales_chart']['data'] = employee_chart_data


    except mysql.connector.Error as err:
        print(f"Error de base de datos al cargar el dashboard: {err}")
        flash(f"Error de base de datos al cargar el dashboard: {str(err)}", "danger")
    except Exception as e:
        print(f"Error inesperado al cargar el dashboard de admin: {e}")
        flash(f"Error inesperado al cargar el dashboard: {str(e)}", "danger")
    finally:
        if conn:
            cursor.close()
            conn.close()

    return render_template('dashboard_admin.html', full_name=full_name, stats=stats)

# RUTA PARA GESTIONAR PRODUCTOS (ADMINISTRADOR)
@app.route('/manage_products', methods=['GET', 'POST'])
def manage_products_view():
    user_id = session.get('user_id')
    user_role = session.get('role')

    if not user_id or user_role != 'admin':
        flash('Acceso denegado. Solo los administradores pueden gestionar productos.', 'danger')
        return redirect(url_for('login_view'))

    conn = None
    cursor = None
    products = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if request.method == 'POST':
            action = request.form.get('action')

            if action == 'add':
                name = request.form['name']
                description = request.form['description']
                price = float(request.form['price'])
                stock = int(request.form['stock'])
                
                cursor.execute(
                    "INSERT INTO products (name, description, price, stock) VALUES (%s, %s, %s, %s)",
                    (name, description, price, stock)
                )
                conn.commit()
                flash('Producto añadido exitosamente!', 'success')
                return redirect(url_for('manage_products_view'))

            elif action == 'edit':
                product_id = request.form['product_id']
                name = request.form['name']
                description = request.form['description']
                price = float(request.form['price'])
                stock = int(request.form['stock'])

                cursor.execute(
                    "UPDATE products SET name = %s, description = %s, price = %s, stock = %s WHERE id = %s",
                    (name, description, price, stock, product_id)
                )
                conn.commit()
                flash('Producto actualizado exitosamente!', 'success')
                return redirect(url_for('manage_products_view'))

            elif action == 'delete':
                product_id = request.form['product_id']
                cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
                conn.commit()
                flash('Producto eliminado exitosamente!', 'success')
                return redirect(url_for('manage_products_view'))

        # Obtener todos los productos para mostrarlos en la tabla
        # MODIFICACIÓN CLAVE AQUÍ: Cambiado de ORDER BY name a ORDER BY id ASC
        cursor.execute("SELECT id, name, description, price, stock FROM products ORDER BY id ASC")
        products = cursor.fetchall()

    except mysql.connector.Error as err:
        flash(f"Error de base de datos: {err}", "danger")
        print(f"Error de base de datos en manage_products_view: {err}")
    except Exception as e:
        flash(f"Error inesperado: {e}", "danger")
        print(f"Error inesperado en manage_products_view: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return render_template('manage_products.html', products=products)


# --- RUTA PARA GESTIONAR USUARIOS (ADMINISTRADOR) ---
@app.route('/manage_users')
def manage_users_view():
    user_id = session.get('user_id')
    user_role = session.get('role')

    if not user_id or user_role != 'admin':
        flash('Acceso denegado. Solo los administradores pueden gestionar usuarios.', 'danger')
        return redirect(url_for('login_view'))

    conn = None
    users = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # MODIFICACIÓN CLAVE AQUÍ: Selecciona TODOS los usuarios, sin filtrar por activo
        cursor.execute("SELECT id, username, first_name, last_name, email, phone, address, dni, role, is_active FROM users")
        users = cursor.fetchall()
    except mysql.connector.Error as err:
        print(f"Error de base de datos al cargar usuarios: {err}")
        flash(f"Error de base de datos: {str(err)}", "danger")
    except Exception as e:
        print(f"Error inesperado al cargar usuarios: {e}")
        flash(f"Error inesperado: {str(e)}", "danger")
    finally:
        if conn:
            conn.close()
    return render_template('manage_users.html', users=users)


# --- RUTA PARA REGISTRAR NUEVOS USUARIOS ---
@app.route('/register_user', methods=['GET', 'POST'])
def register_user_view():
    user_id = session.get('user_id')
    user_role = session.get('role')

    # Solo administradores pueden registrar usuarios
    if not user_id or user_role != 'admin':
        flash('Acceso denegado. Solo los administradores pueden registrar nuevos usuarios.', 'danger')
        return redirect(url_for('login_view'))

    if request.method == 'POST':
        # Obtener los datos del formulario
        username = request.form.get('username')
        password = request.form.get('password')
        hashed_password = generate_password_hash(password)  # ✅ Hashear la contraseña aquí
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        address = request.form.get('address')
        dni = request.form.get('dni')
        role = request.form.get('role', 'employee')

        if not all([username, password, first_name, last_name, email, role]):
            flash('Por favor, complete todos los campos obligatorios.', 'danger')
            return render_template('register_user.html',
                                   username=username, first_name=first_name,
                                   last_name=last_name, email=email,
                                   phone=phone, address=address, dni=dni, role=role)

        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Verificar si el nombre de usuario o email ya existen
            cursor.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
            existing_user = cursor.fetchone()
            if existing_user:
                flash('El nombre de usuario o el email ya están registrados.', 'warning')
                return render_template('register_user.html',
                                       username=username, first_name=first_name,
                                       last_name=last_name, email=email,
                                       phone=phone, address=address, dni=dni, role=role)

            # ✅ Usar el hash en lugar de la contraseña en texto plano
            cursor.execute(
                "INSERT INTO users (username, password_hash, first_name, last_name, email, phone, address, dni, role) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (username, hashed_password, first_name, last_name, email, phone, address, dni, role)
            )
            conn.commit()
            flash('Usuario registrado exitosamente!', 'success')
            return redirect(url_for('manage_users_view'))

        except mysql.connector.Error as err:
            flash(f"Error de base de datos al registrar el usuario: {err}", "danger")
            print(f"Error de DB en register_user_view: {err}")
        except Exception as e:
            flash(f"Error inesperado al registrar el usuario: {e}", "danger")
            print(f"Error inesperado en register_user_view: {e}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    return render_template('register_user.html',
                           username='', first_name='', last_name='',
                           email='', phone='', address='', dni='', role='employee')
    
# --- NUEVA RUTA: OBTENER DATOS DE USUARIO PARA EDICIÓN (AJAX) ---
@app.route('/get_user_data/<int:user_id>', methods=['GET'])
def get_user_data(user_id):
    # Protección: solo administradores pueden ver datos de otros usuarios
    if not session.get('user_id') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Acceso denegado.'}), 403

    conn = None
    user_data = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True) # Importante para obtener los resultados como diccionarios
        cursor.execute("SELECT id, username, first_name, last_name, email, phone, address, dni, role FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()

        if user_data:
            # Convertir cualquier None a cadena vacía para evitar 'null' en el formulario
            for key, value in user_data.items():
                if value is None:
                    user_data[key] = ''
            return jsonify(user_data) # Devuelve todos los datos del usuario
        else:
            return jsonify({'success': False, 'message': 'Usuario no encontrado.'}), 404
    except mysql.connector.Error as err:
        print(f"Error de base de datos al obtener datos de usuario: {err}")
        return jsonify({'success': False, 'message': 'Error de base de datos.'}), 500
    except Exception as e:
        print(f"Error inesperado al obtener datos de usuario: {e}")
        return jsonify({'success': False, 'message': 'Error interno del servidor.'}), 500
    finally:
        if conn:
            conn.close()

# --- NUEVA RUTA: EDITAR USUARIO (POST) ---
@app.route('/edit_user/<int:user_id>', methods=['POST'])
def edit_user(user_id):
    # Protección de la ruta para administradores
    if not session.get('user_id') or session.get('role') != 'admin':
        flash('Acceso denegado. Solo los administradores pueden editar usuarios.', 'danger')
        return redirect(url_for('login_view')) # O retornar un jsonify para peticiones AJAX

    # Obtener los datos del formulario (desde el modal)
    username = request.form['username']
    first_name = request.form['first_name']
    last_name = request.form['last_name']
    email = request.form['email']
    phone = request.form.get('phone') # Opcional
    address = request.form.get('address') # Opcional
    dni = request.form.get('dni') # Opcional
    role = request.form['role'] # Nuevo campo de rol
    new_password = request.form.get('password') # Campo para la nueva contraseña

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Construir la parte SET de la consulta dinámicamente
        set_clauses = [
            "username = %s",
            "first_name = %s",
            "last_name = %s",
            "email = %s",
            "phone = %s",
            "address = %s",
            "dni = %s",
            "role = %s" # Añadir rol
        ]
        params = [
            username, first_name, last_name, email, phone, address, dni, role
        ]

        if new_password:
            # Si hay una nueva contraseña, añadirla a la consulta y a los parámetros
            set_clauses.append("password_hash = %s") 
            params.append(new_password)

        query = f"UPDATE users SET {', '.join(set_clauses)} WHERE id = %s"
        params.append(user_id) # Añadir el user_id al final de los parámetros

        cursor.execute(query, tuple(params))
        conn.commit()
        flash('Usuario actualizado correctamente.', 'success')
        return redirect(url_for('manage_users_view'))
    except mysql.connector.Error as err:
        flash(f"Error de base de datos al actualizar usuario: {err}", "danger")
        print(f"Error de base de datos en edit_user: {err}")
    except Exception as e:
        flash(f"Error inesperado al actualizar usuario: {e}", "danger")
        print(f"Error inesperado en edit_user: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('manage_users_view'))

# --- NUEVA RUTA: ELIMINAR USUARIO (POST) ---
@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    current_user_id = session.get('user_id')
    user_role = session.get('role')

    if not current_user_id or user_role != 'admin':
        flash('Acceso denegado. Solo los administradores pueden realizar esta acción.', 'danger')
        return redirect(url_for('login_view'))

    if user_id == current_user_id:
        flash('No puedes eliminar tu propia cuenta mientras estás logueado.', 'danger')
        return redirect(url_for('manage_users_view'))

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True) # Usar dictionary=True para acceder por nombre de columna

        # 1. Obtener el nombre de usuario para el mensaje de flash
        cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        username = user_data['username'] if user_data else f"Usuario con ID {user_id}"

        # 2. Verificar si el usuario tiene ventas vinculadas
        # CORRECCIÓN: Cambiar 'user_id' a 'employee_id' en la cláusula WHERE
        cursor.execute("SELECT COUNT(*) AS sales_count FROM sales WHERE employee_id = %s", (user_id,))
        result = cursor.fetchone()
        sales_count = result['sales_count'] if result else 0

        if sales_count > 0:
            # Si tiene ventas vinculadas, NO ELIMINAR FÍSICAMENTE.
            # En su lugar, marcar como inactivo.
            cursor.execute("UPDATE users SET is_active = FALSE WHERE id = %s", (user_id,))
            conn.commit()
            flash(f'El usuario "{username}" tiene {sales_count} ventas vinculadas. Se ha marcado como INACTIVO para mantener la integridad de los datos.', 'warning')
        else:
            # Si no tiene ventas vinculadas, se puede eliminar físicamente.
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
            flash(f'Usuario "{username}" eliminado correctamente.', 'success')

    except mysql.connector.Error as err:
        print(f"Error de base de datos al gestionar eliminación/inactivación de usuario: {err}")
        flash(f"Error de base de datos al gestionar usuario: {str(err)}", "danger")
    except Exception as e:
        print(f"Error inesperado al gestionar eliminación/inactivación de usuario: {e}")
        flash(f"Error inesperado al gestionar usuario: {str(e)}", "danger")
    finally:
        if conn:
            conn.close()

    return redirect(url_for('manage_users_view'))

#RUTA PARA ACTIVAR USUARIO (POST)
@app.route('/activate_user/<int:user_id>', methods=['POST'])
def activate_user(user_id):
    current_user_id = session.get('user_id')
    user_role = session.get('role')

    if not current_user_id or user_role != 'admin':
        flash('Acceso denegado. Solo los administradores pueden realizar esta acción.', 'danger')
        return redirect(url_for('login_view'))

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Obtener el nombre de usuario para el mensaje de flash
        cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        username = user_data['username'] if user_data else f"Usuario con ID {user_id}"

        # Actualizar el estado a activo
        cursor.execute("UPDATE users SET is_active = TRUE WHERE id = %s", (user_id,))
        conn.commit()
        flash(f'Usuario "{username}" activado correctamente.', 'success')

    except mysql.connector.Error as err:
        print(f"Error de base de datos al activar usuario: {err}")
        flash(f"Error de base de datos al activar usuario: {str(err)}", "danger")
    except Exception as e:
        print(f"Error inesperado al activar usuario: {e}")
        flash(f"Error inesperado al activar usuario: {str(e)}", "danger")
    finally:
        if conn:
            conn.close()

    return redirect(url_for('manage_users_view'))


# RUTA PARA REPORTES Y BOLETAS (Debe reemplazar a admin_reports_view si existía)
@app.route('/admin_boletas_reports', methods=['GET'])
def admin_boletas_reports_view():
    user_id = session.get('user_id')
    user_role = session.get('role')

    if not user_id or user_role != 'admin':
        flash('Acceso denegado. Solo los administradores pueden acceder a esta sección.', 'danger')
        return redirect(url_for('login_view'))

    conn = None
    cursor = None
    sales_data = []
    employees = []
    selected_employee_id = request.args.get('employee_id', type=int)

    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)

            # 1. Obtener la lista de empleados para el filtro
            cursor.execute("SELECT id, first_name, last_name FROM users WHERE role = 'employee' AND is_active = 1 ORDER BY first_name, last_name")
            employees = cursor.fetchall()
            employees.insert(0, {'id': 0, 'first_name': 'Todos', 'last_name': 'los Empleados'})

            # 2. Obtener todas las ventas con información del empleado y estado de anulación
            query = """
                SELECT
                    s.id AS sale_id,
                    s.sale_date,
                    s.total_amount,
                    s.payment_method,
                    s.is_cancelled,
                    u.first_name AS employee_first_name,
                    u.last_name AS employee_last_name
                FROM sales s
                JOIN users u ON s.employee_id = u.id -- <<<< CORREGIDO AQUÍ: s.user_id -> s.employee_id
            """
            params = []

            if selected_employee_id is not None and selected_employee_id != 0:
                query += " WHERE s.employee_id = %s" # <<<< CORREGIDO AQUÍ: s.user_id -> s.employee_id
                params.append(selected_employee_id)

            query += " ORDER BY s.sale_date DESC"

            cursor.execute(query, tuple(params))
            sales_data = cursor.fetchall()

            for sale in sales_data:
                if isinstance(sale['sale_date'], (datetime, date)):
                    sale['sale_date_formatted'] = sale['sale_date'].strftime('%d-%m-%Y %H:%M')
                elif isinstance(sale['sale_date'], str):
                    try:
                        dt_obj = datetime.strptime(sale['sale_date'], '%Y-%m-%d %H:%M:%S')
                        sale['sale_date_formatted'] = dt_obj.strftime('%d-%m-%Y %H:%M')
                    except ValueError:
                        try:
                            dt_obj = datetime.strptime(sale['sale_date'], '%Y-%m-%d')
                            sale['sale_date_formatted'] = dt_obj.strftime('%d-%m-%Y')
                        except ValueError:
                            sale['sale_date_formatted'] = str(sale['sale_date'])
                else:
                    sale['sale_date_formatted'] = str(sale['sale_date'])

    except mysql.connector.Error as err:
        print(f"Error de base de datos al cargar reportes de boletas: {err}")
        flash(f"Error de base de datos: {str(err)}", "danger")
    except Exception as e:
        print(f"Error inesperado al cargar reportes de boletas: {e}")
        flash(f"Error inesperado: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
            print("Conexión a DB cerrada para reportes de boletas.")

    return render_template('admin_boletas_reports.html',
                            sales=sales_data,
                            employees=employees,
                            selected_employee_id=selected_employee_id)


# ====================================================================
# RUTA PARA ANULAR UNA VENTA (BOLETA)
# ====================================================================
@app.route('/cancel_sale/<int:sale_id>', methods=['POST'])
def cancel_sale(sale_id):
    # Protección: solo administradores pueden anular ventas
    if not session.get('user_id') or session.get('role') != 'admin':
        flash('Acceso denegado. Solo los administradores pueden anular ventas.', 'danger')
        return redirect(url_for('login_view'))

    conn = None
    cursor = None # Asegurarse de inicializar el cursor a None
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()

            # Verificar si la boleta ya está anulada para evitar errores lógicos o re-anulaciones innecesarias
            cursor.execute("SELECT is_cancelled FROM sales WHERE id = %s", (sale_id,))
            current_status = cursor.fetchone()

            if current_status is None:
                flash(f'Boleta #{sale_id} no encontrada.', 'danger')
                return redirect(url_for('admin_boletas_reports_view'))
            
            if current_status[0] == 1: # current_status[0] porque fetchone devuelve una tupla para un solo valor
                flash(f'Boleta #{sale_id} ya se encuentra anulada.', 'info')
                return redirect(url_for('admin_boletas_reports_view'))

            # Actualizar el estado is_cancelled a 1 (true) para la venta específica
            cursor.execute("UPDATE sales SET is_cancelled = 1 WHERE id = %s", (sale_id,))
            conn.commit()

            flash(f'Boleta #{sale_id} anulada correctamente.', 'success')
            return redirect(url_for('admin_boletas_reports_view'))

    except mysql.connector.Error as err:
        flash(f"Error de base de datos al anular boleta: {err}", "danger")
        print(f"Error de base de datos en cancel_sale: {err}")
    except Exception as e:
        flash(f"Error inesperado al anular boleta: {e}", "danger")
        print(f"Error inesperado en cancel_sale: {e}")
    finally:
        if cursor: # Cerrar cursor si existe
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
            print("Conexión a DB cerrada para anular boleta.")
    return redirect(url_for('admin_boletas_reports_view'))



if __name__ == '__main__':
    app.run(debug=True)
