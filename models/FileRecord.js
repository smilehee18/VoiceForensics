const mongoose = require('mongoose');

const fileControlSchema = new mongoose.Schema({
  filename: String,
  path: String
});

const FileControl = mongoose.model('FileRecord', fileRecordSchema);

module.exports = FileRecord;