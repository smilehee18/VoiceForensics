// models/Result.js
const mongoose = require('mongoose');

const resultsSchema = new mongoose.Schema({
  files_control_id: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'FileControl'
  },
  files_record_id: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'FileRecord'
  },
  bool: Boolean,
  percent: Number,
  date: {
    type: Date,
    default: Date.now
  }
});

mongoose.set('strictQuery', true);
module.exports = mongoose.model('Result', resultsSchema);
