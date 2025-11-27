const express = require('express');
const cors = require('cors');
const mysql = require('mysql2/promise');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 5000;

// Middleware
app.use(cors());
app.use(express.json());

// MySQL Connection Pool
const pool = mysql.createPool({
  host: process.env.DB_HOST || 'localhost',
  user: process.env.DB_USER || 'root',
  password: process.env.DB_PASSWORD || '',
  database: process.env.DB_NAME || 'smarttrashbin',
  waitForConnections: true,
  connectionLimit: 10,
  queueLimit: 0
});

// Test database connection
pool.getConnection()
  .then(connection => {
    console.log('✅ MySQL Connected');
    connection.release();
  })
  .catch(err => {
    console.error('❌ MySQL Connection Error:', err.message);
  });

// Data terakhir (untuk quick access tanpa query)
let latestSensorData = {
  fill_percentage: 0,
  distance_cm: 0,
  led_status: 'green',
  trash_condition: 'empty',
  gas_ppm: 0,
  gas_level_status: 'safe',
  buzzer_status: 'off',
  created_at: new Date().toISOString()
};

// Helper: Determine trash condition
function getTrashCondition(fillPercentage) {
  if (fillPercentage < 30) return 'empty';
  if (fillPercentage >= 30 && fillPercentage < 70) return 'half';
  return 'full';
}

// Helper: Determine LED status
function getLedStatus(fillPercentage) {
  if (fillPercentage < 30) return 'green';
  if (fillPercentage >= 30 && fillPercentage < 70) return 'yellow';
  return 'red';
}

// Helper: Determine gas level status
function getGasLevelStatus(gasPPM) {
  if (gasPPM < 300) return 'safe';
  if (gasPPM >= 300 && gasPPM < 700) return 'warning';
  return 'danger';
}

// Helper: Determine buzzer status
function getBuzzerStatus(fillPercentage, gasPPM) {
  if (fillPercentage >= 70 || gasPPM >= 700) return 'on';
  return 'off';
}

// Endpoint: Get latest sensor data
app.get('/api/sensor-data', async (req, res) => {
  try {
    const [rows] = await pool.query(
      'SELECT * FROM trashbin_status ORDER BY created_at DESC LIMIT 1'
    );
    
    if (rows.length > 0) {
      latestSensorData = rows[0];
    }
    
    res.json({
      success: true,
      data: latestSensorData
    });
  } catch (error) {
    console.error('Error fetching data:', error);
    res.json({
      success: true,
      data: latestSensorData // fallback to cached data
    });
  }
});

// Endpoint: Get sensor history
app.get('/api/sensor-history', async (req, res) => {
  try {
    const limit = parseInt(req.query.limit) || 100;
    const hours = parseInt(req.query.hours) || 24;
    
    const [rows] = await pool.query(
      `SELECT * FROM trashbin_status 
       WHERE created_at >= DATE_SUB(NOW(), INTERVAL ? HOUR)
       ORDER BY created_at DESC 
       LIMIT ?`,
      [hours, limit]
    );
    
    res.json({
      success: true,
      count: rows.length,
      data: rows
    });
  } catch (error) {
    console.error('Error fetching history:', error);
    res.status(500).json({
      success: false,
      message: 'Error fetching history',
      error: error.message
    });
  }
});

// Endpoint: Get statistics
app.get('/api/statistics', async (req, res) => {
  try {
    const hours = parseInt(req.query.hours) || 24;
    
    const [rows] = await pool.query(
      `SELECT 
        AVG(fill_percentage) as avgFillPercentage,
        MAX(fill_percentage) as maxFillPercentage,
        MIN(fill_percentage) as minFillPercentage,
        AVG(gas_ppm) as avgGasPPM,
        MAX(gas_ppm) as maxGasPPM,
        COUNT(*) as totalRecords
       FROM trashbin_status 
       WHERE created_at >= DATE_SUB(NOW(), INTERVAL ? HOUR)`,
      [hours]
    );
    
    res.json({
      success: true,
      data: rows[0] || {}
    });
  } catch (error) {
    console.error('Error fetching statistics:', error);
    res.status(500).json({
      success: false,
      message: 'Error fetching statistics',
      error: error.message
    });
  }
});

// Endpoint: Update sensor data (dari Raspberry Pi)
app.post('/api/sensor-data', async (req, res) => {
  try {
    const { fill_percentage, distance_cm, gas_ppm } = req.body;
    
    // Validasi input
    if (fill_percentage === undefined || distance_cm === undefined) {
      return res.status(400).json({
        success: false,
        message: 'fill_percentage dan distance_cm wajib diisi'
      });
    }
    
    // Hitung status otomatis
    const trash_condition = getTrashCondition(fill_percentage);
    const led_status = getLedStatus(fill_percentage);
    const gas_level_status = getGasLevelStatus(gas_ppm || 0);
    const buzzer_status = getBuzzerStatus(fill_percentage, gas_ppm || 0);
    
    // Insert ke database
    const [result] = await pool.query(
      `INSERT INTO trashbin_status 
       (fill_percentage, distance_cm, led_status, trash_condition, gas_ppm, gas_level_status, buzzer_status) 
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [fill_percentage, distance_cm, led_status, trash_condition, gas_ppm || 0, gas_level_status, buzzer_status]
    );
    
    // Update cache
    latestSensorData = {
      id: result.insertId,
      fill_percentage,
      distance_cm,
      led_status,
      trash_condition,
      gas_ppm: gas_ppm || 0,
      gas_level_status,
      buzzer_status,
      created_at: new Date().toISOString()
    };
    
    console.log('✅ Data saved to DB:', latestSensorData);
    
    res.json({
      success: true,
      message: 'Data berhasil disimpan',
      data: latestSensorData
    });
  } catch (error) {
    console.error('❌ Error saving data:', error);
    res.status(500).json({
      success: false,
      message: 'Error menyimpan data',
      error: error.message
    });
  }
});

// Endpoint: Simulasi data
app.post('/api/simulate', async (req, res) => {
  try {
    const fill_percentage = Math.floor(Math.random() * 100);
    const distance_cm = Math.floor(Math.random() * 30);
    const gas_ppm = Math.floor(Math.random() * 1000);
    
    const trash_condition = getTrashCondition(fill_percentage);
    const led_status = getLedStatus(fill_percentage);
    const gas_level_status = getGasLevelStatus(gas_ppm);
    const buzzer_status = getBuzzerStatus(fill_percentage, gas_ppm);
    
    // Insert ke database
    const [result] = await pool.query(
      `INSERT INTO trashbin_status 
       (fill_percentage, distance_cm, led_status, trash_condition, gas_ppm, gas_level_status, buzzer_status) 
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [fill_percentage, distance_cm, led_status, trash_condition, gas_ppm, gas_level_status, buzzer_status]
    );
    
    latestSensorData = {
      id: result.insertId,
      fill_percentage,
      distance_cm,
      led_status,
      trash_condition,
      gas_ppm,
      gas_level_status,
      buzzer_status,
      created_at: new Date().toISOString()
    };
    
    res.json({
      success: true,
      message: 'Simulasi data berhasil',
      data: latestSensorData
    });
  } catch (error) {
    console.error('Error simulating data:', error);
    res.status(500).json({
      success: false,
      message: 'Error simulasi data',
      error: error.message
    });
  }
});

// Endpoint: Delete old data (cleanup)
app.delete('/api/sensor-data/cleanup', async (req, res) => {
  try {
    const days = parseInt(req.query.days) || 7;
    
    const [result] = await pool.query(
      'DELETE FROM trashbin_status WHERE created_at < DATE_SUB(NOW(), INTERVAL ? DAY)',
      [days]
    );
    
    res.json({
      success: true,
      message: `Data lebih dari ${days} hari dihapus`,
      deletedCount: result.affectedRows
    });
  } catch (error) {
    console.error('Error cleanup data:', error);
    res.status(500).json({
      success: false,
      message: 'Error cleanup data',
      error: error.message
    });
  }
});

// Health check
app.get('/api/health', async (req, res) => {
  let dbStatus = 'Disconnected';
  
  try {
    await pool.query('SELECT 1');
    dbStatus = 'Connected';
  } catch (error) {
    dbStatus = 'Error: ' + error.message;
  }
  
  res.json({
    status: 'OK',
    database: dbStatus,
    timestamp: new Date().toISOString()
  });
});

// Start server
app.listen(PORT, () => {
  console.log(`🚀 Server berjalan di http://localhost:${PORT}`);
  console.log(`📊 API Endpoint: http://localhost:${PORT}/api/sensor-data`);
  console.log(`📈 History: http://localhost:${PORT}/api/sensor-history`);
  console.log(`📉 Statistics: http://localhost:${PORT}/api/statistics`);
});