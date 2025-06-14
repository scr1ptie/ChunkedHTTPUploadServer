#!/usr/bin/env python3
 
import os, sys
import os.path, time
import posixpath
import http.server
import socketserver
import urllib.request, urllib.parse, urllib.error
import html
import shutil
import mimetypes
import re
import argparse
import base64

from io import BytesIO

def fbytes(B):
   'Return the given bytes as a human friendly KB, MB, GB, or TB string'
   B = float(B)
   KB = float(1024)
   MB = float(KB ** 2) # 1,048,576
   GB = float(KB ** 3) # 1,073,741,824
   TB = float(KB ** 4) # 1,099,511,627,776

   if B < KB:
      return '{0} {1}'.format(B,'Bytes' if 0 == B > 1 else 'Byte')
   elif KB <= B < MB:
      return '{0:.2f} KB'.format(B/KB)
   elif MB <= B < GB:
      return '{0:.2f} MB'.format(B/MB)
   elif GB <= B < TB:
      return '{0:.2f} GB'.format(B/GB)
   elif TB <= B:
      return '{0:.2f} TB'.format(B/TB)

class SimpleHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
 
    """Simple HTTP request handler with GET/HEAD/POST commands.

    This serves files from the current directory and any of its
    subdirectories.  The MIME type for files is determined by
    calling the .guess_type() method. And can reveive file uploaded
    by client.

    The GET/HEAD/POST requests are identical except that the HEAD
    request omits the actual contents of the file.

    """
 
    server_version = "SimpleHTTPWithUpload/" + __version__
 
    def do_GET(self):
        """Serve a GET request."""
        if self.path == '/upload.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            # Serve the upload page directly
            upload_html = """<!DOCTYPE html>
<html>
<head>
    <title>Chunked File Upload</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }
        .upload-container {
            border: 2px dashed #ccc;
            border-radius: 10px;
            padding: 40px;
            text-align: center;
            margin: 20px 0;
        }
        .upload-container.dragover {
            border-color: #007bff;
            background-color: #f8f9fa;
        }
        .file-input {
            margin: 20px 0;
        }
        .progress-container {
            margin: 20px 0;
            display: none;
        }
        .progress-bar {
            width: 100%;
            height: 20px;
            background-color: #f0f0f0;
            border-radius: 10px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            background-color: #007bff;
            width: 0%;
            transition: width 0.3s ease;
        }
        .progress-text {
            margin-top: 10px;
            font-size: 14px;
            color: #666;
        }
        .upload-btn {
            background-color: #007bff;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
        }
        .upload-btn:hover {
            background-color: #0056b3;
        }
        .upload-btn:disabled {
            background-color: #ccc;
            cursor: not-allowed;
        }
        .status {
            margin: 20px 0;
            padding: 10px;
            border-radius: 5px;
        }
        .status.success {
            background-color: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .status.error {
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
    </style>
</head>
<body>
    <h1>Chunked File Upload</h1>
    <p>Upload large files by splitting them into chunks smaller than 100MB to work around Cloudflare limits.</p>
    
    <div class="upload-container" id="uploadContainer">
        <div>
            <p>Drag and drop files here or click to select</p>
            <input type="file" id="fileInput" class="file-input" multiple>
        </div>
    </div>
    
    <button id="uploadBtn" class="upload-btn" onclick="startUpload()" disabled>Upload Files</button>
    
    <div class="progress-container" id="progressContainer">
        <div class="progress-bar">
            <div class="progress-fill" id="progressFill"></div>
        </div>
        <div class="progress-text" id="progressText">Ready to upload...</div>
    </div>
    
    <div id="status"></div>

    <script>
        const CHUNK_SIZE = 90 * 1024 * 1024; // 90MB chunks (under Cloudflare's 100MB limit)
        let selectedFiles = [];
        let isUploading = false;

        // DOM elements
        const uploadContainer = document.getElementById('uploadContainer');
        const fileInput = document.getElementById('fileInput');
        const uploadBtn = document.getElementById('uploadBtn');
        const progressContainer = document.getElementById('progressContainer');
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        const statusDiv = document.getElementById('status');

        // File input change handler
        fileInput.addEventListener('change', handleFileSelect);
        
        // Drag and drop handlers
        uploadContainer.addEventListener('dragover', handleDragOver);
        uploadContainer.addEventListener('dragleave', handleDragLeave);
        uploadContainer.addEventListener('drop', handleDrop);
        uploadContainer.addEventListener('click', () => fileInput.click());

        function handleFileSelect(event) {
            selectedFiles = Array.from(event.target.files);
            updateUI();
        }

        function handleDragOver(event) {
            event.preventDefault();
            uploadContainer.classList.add('dragover');
        }

        function handleDragLeave(event) {
            event.preventDefault();
            uploadContainer.classList.remove('dragover');
        }

        function handleDrop(event) {
            event.preventDefault();
            uploadContainer.classList.remove('dragover');
            selectedFiles = Array.from(event.dataTransfer.files);
            updateUI();
        }

        function updateUI() {
            if (selectedFiles.length > 0) {
                uploadBtn.disabled = false;
                const totalSize = selectedFiles.reduce((sum, file) => sum + file.size, 0);
                uploadContainer.innerHTML = `
                    <p>${selectedFiles.length} file(s) selected</p>
                    <p>Total size: ${formatBytes(totalSize)}</p>
                    <p>Click to select different files</p>
                `;
            } else {
                uploadBtn.disabled = true;
                uploadContainer.innerHTML = `
                    <p>Drag and drop files here or click to select</p>
                `;
            }
        }

        async function startUpload() {
            if (isUploading || selectedFiles.length === 0) return;
            
            isUploading = true;
            uploadBtn.disabled = true;
            progressContainer.style.display = 'block';
            statusDiv.innerHTML = '';

            try {
                for (let i = 0; i < selectedFiles.length; i++) {
                    const file = selectedFiles[i];
                    showStatus(`Uploading ${file.name}...`, 'info');
                    await uploadFileInChunks(file, i, selectedFiles.length);
                }
                showStatus('All files uploaded successfully!', 'success');
            } catch (error) {
                showStatus(`Upload failed: ${error.message}`, 'error');
            } finally {
                isUploading = false;
                uploadBtn.disabled = false;
                progressContainer.style.display = 'none';
            }
        }

        async function uploadFileInChunks(file, fileIndex, totalFiles) {
            const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
            
            // Upload each chunk
            for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
                const start = chunkIndex * CHUNK_SIZE;
                const end = Math.min(start + CHUNK_SIZE, file.size);
                const chunk = file.slice(start, end);
                
                const overallProgress = ((fileIndex * 100) + ((chunkIndex + 1) / totalChunks * 100)) / totalFiles;
                updateProgress(overallProgress, `Uploading ${file.name} - Chunk ${chunkIndex + 1}/${totalChunks}`);
                
                await uploadChunk(chunk, chunkIndex, totalChunks, file.name);
            }
            
            // Finalize the upload
            await finalizeUpload(file.name, totalChunks);
        }

        async function uploadChunk(chunk, chunkIndex, totalChunks, filename) {
            const url = `/upload_chunk?chunk=${chunkIndex}&total=${totalChunks}&filename=${encodeURIComponent(filename)}`;
            
            const response = await fetch(url, {
                method: 'POST',
                body: chunk,
                headers: {
                    'Content-Type': 'application/octet-stream'
                }
            });
            
            if (!response.ok) {
                throw new Error(`Failed to upload chunk ${chunkIndex + 1}: ${response.statusText}`);
            }
        }

        async function finalizeUpload(filename, totalChunks) {
            const url = `/finalize_upload?filename=${encodeURIComponent(filename)}&total=${totalChunks}`;
            
            const response = await fetch(url, {
                method: 'POST'
            });
            
            if (!response.ok) {
                throw new Error(`Failed to finalize upload: ${response.statusText}`);
            }
        }

        function updateProgress(percentage, text) {
            progressFill.style.width = `${percentage}%`;
            progressText.textContent = text;
        }

        function showStatus(message, type) {
            statusDiv.innerHTML = `<div class="status ${type}">${message}</div>`;
        }

        function formatBytes(bytes, decimals = 2) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const dm = decimals < 0 ? 0 : decimals;
            const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
        }
    </script>
</body>
</html>"""
            self.wfile.write(upload_html.encode('utf-8'))
            return
            
        # Handle all other GET requests normally
        f = self.send_head()
        if f:
            self.copyfile(f, self.wfile)
            f.close()
 
    def do_HEAD(self):
        """Serve a HEAD request."""
        f = self.send_head()
        if f:
            f.close()
 
    def do_POST(self):
        """Serve a POST request."""
        # Check if this is a chunked upload request
        if self.path.startswith('/upload_chunk'):
            r, info = self.handle_chunk_upload()
        elif self.path.startswith('/finalize_upload'):
            r, info = self.handle_finalize_upload()
        else:
            r, info = self.deal_post_data()
        
        print((r, info, "by: ", self.client_address))
        f = BytesIO()
        f.write(b'<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">')
        f.write(b"<html>\n<title>Upload Result Page</title>\n")
        f.write(b'<style type="text/css">\n')
        f.write(b'* {font-family: Helvetica; font-size: 16px; }\n')
        f.write(b'a { text-decoration: none; }\n')
        f.write(b'</style>\n')
        f.write(b"<body>\n<h2>Upload Result Page</h2>\n")
        f.write(b"<hr>\n")
        if r:
            f.write(b"<strong>Success!</strong>")
        else:
            f.write(b"<strong>Failed!</strong>")
        f.write(info.encode())
        f.write(("<br><br><a href=\"%s\">" % self.headers.get('referer', '/')).encode())
        f.write(b"<button>Back</button></a>\n")
        f.write(b"<hr><small>Powered By: bones7456<br>Check new version ")
        f.write(b"<a href=\"https://gist.github.com/UniIsland/3346170\" target=\"_blank\">")
        f.write(b"here</a>.</small></body>\n</html>\n")
        length = f.tell()
        f.seek(0)
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        if f:
            self.copyfile(f, self.wfile)
            f.close()

    def deal_post_data(self):
        uploaded_files = []   
        content_type = self.headers['content-type']
        if not content_type:
            return (False, "Content-Type header doesn't contain boundary")
        
        # Extract boundary from content-type header
        boundary = content_type.split("=")[1].encode()
        remainbytes = int(self.headers['content-length'])
        
        # Define chunk size (50MB)
        max_chunk_size = 50 * 1024 * 1024  # 50MB chunks
        
        print(f"Starting upload processing. Total size: {fbytes(remainbytes)}")
        
        # Read initial boundary line
        line = self.rfile.readline()
        remainbytes -= len(line)
        if not boundary in line:
            return (False, "Content NOT begin with boundary")
            
        while remainbytes > 0:
            # Read headers for this part
            line = self.rfile.readline()
            remainbytes -= len(line)
            
            # Extract filename from Content-Disposition header
            fn = re.findall(r'Content-Disposition.*name="file"; filename="(.*)"', line.decode())
            if not fn:
                return (False, "Can't find out file name...")
                
            path = self.translate_path(self.path)
            fn = os.path.join(path, fn[0])
            print(f"Processing file: {os.path.basename(fn)}")
            
            # Skip Content-Type header if present
            line = self.rfile.readline()
            remainbytes -= len(line)
            
            # Skip empty line after headers
            line = self.rfile.readline()
            remainbytes -= len(line)
            
            try:
                out = open(fn, 'wb')
            except IOError:
                return (False, "<br><br>Can't create file to write.<br>Do you have permission to write?")
            
            # Process file data in chunks
            with out:
                bytes_written = 0
                buffer = b''
                
                while remainbytes > 0:
                    # Determine how much to read in this iteration
                    read_size = min(max_chunk_size, remainbytes, 65536)  # 64KB buffer max
                    
                    # Read chunk
                    chunk = self.rfile.read(read_size)
                    if not chunk:
                        break
                        
                    remainbytes -= len(chunk)
                    buffer += chunk
                    
                    # Check for boundary in buffer
                    boundary_pos = buffer.find(boundary)
                    
                    if boundary_pos != -1:
                        # Found boundary - write data before boundary
                        file_data = buffer[:boundary_pos]
                        
                        # Remove trailing CRLF before boundary
                        if file_data.endswith(b'\r\n'):
                            file_data = file_data[:-2]
                        elif file_data.endswith(b'\n'):
                            file_data = file_data[:-1]
                            
                        out.write(file_data)
                        bytes_written += len(file_data)
                        
                        # Update remaining bytes (skip past boundary)
                        remaining_buffer = buffer[boundary_pos:]
                        remainbytes += len(remaining_buffer) - len(buffer)
                        
                        uploaded_files.append(fn)
                        print(f"Successfully uploaded: {os.path.basename(fn)} ({fbytes(bytes_written)})")
                        break
                    else:
                        # No boundary found yet
                        if len(buffer) > max_chunk_size:
                            # Write most of buffer, keep some for boundary detection
                            keep_size = len(boundary) + 10  # Keep extra for CRLF
                            write_data = buffer[:-keep_size]
                            buffer = buffer[-keep_size:]
                            
                            out.write(write_data)
                            bytes_written += len(write_data)
                            
                            # Progress update every 10MB
                            if bytes_written % (10 * 1024 * 1024) == 0:
                                print(f"Uploaded {fbytes(bytes_written)} of {os.path.basename(fn)}")
                
                # Handle case where file ends without explicit boundary
                if remainbytes <= 0 and fn not in uploaded_files:
                    if buffer and not boundary in buffer:
                        # Remove trailing CRLF
                        if buffer.endswith(b'\r\n'):
                            buffer = buffer[:-2]
                        elif buffer.endswith(b'\n'):
                            buffer = buffer[:-1]
                        out.write(buffer)
                        bytes_written += len(buffer)
                    uploaded_files.append(fn)
                    print(f"Successfully uploaded: {os.path.basename(fn)} ({fbytes(bytes_written)})")
                    
        return (True, "<br><br>'%s'" % "'<br>'".join([os.path.basename(f) for f in uploaded_files]))

    def _read_chunk_safely(self, max_size, boundary):
        """Read data in chunks while checking for boundary markers.
        Returns None if boundary is found, otherwise returns the chunk data."""
        chunk = b''
        bytes_to_read = min(max_size, 8192)  # Read in 8KB increments
        
        while len(chunk) < max_size:
            try:
                data = self.rfile.read(bytes_to_read)
                if not data:
                    break
                    
                # Check if boundary is in this data
                if boundary in data:
                    # Find boundary position and return data up to boundary
                    boundary_pos = data.find(boundary)
                    if boundary_pos > 0:
                        chunk += data[:boundary_pos]
                    return None  # Signal boundary found
                    
                chunk += data
                
                # Adjust remaining bytes to read
                remaining = max_size - len(chunk)
                bytes_to_read = min(remaining, 8192)
                
            except Exception as e:
                print(f"Error reading chunk: {e}")
                break
                
        return chunk if chunk else None

    def send_head(self):
        """Common code for GET and HEAD commands.

        This sends the response code and MIME headers.

        Return value is either a file object (which has to be copied
        to the outputfile by the caller unless the command was HEAD,
        and must be closed by the caller under all circumstances), or
        None, in which case the caller has nothing further to do.

        """
        path = self.translate_path(self.path)
        f = None
        if os.path.isdir(path):
            if not self.path.endswith('/'):
                # redirect browser - doing basically what apache does
                self.send_response(301)
                self.send_header("Location", self.path + "/")
                self.end_headers()
                return None
            for index in "index.html", "index.htm":
                index = os.path.join(path, index)
                if os.path.exists(index):
                    path = index
                    break
            else:
                return self.list_directory(path)
        ctype = self.guess_type(path)
        try:
            # Always read in binary mode. Opening files in text mode may cause
            # newline translations, making the actual size of the content
            # transmitted *less* than the content-length!
            f = open(path, 'rb')
        except IOError:
            self.send_error(404, "File not found")
            return None
        self.send_response(200)
        self.send_header("Content-type", ctype)
        fs = os.fstat(f.fileno())
        self.send_header("Content-Length", str(fs[6]))
        self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
        self.end_headers()
        return f
 


    def list_directory(self, path):
        """Helper to produce a directory listing (absent index.html).

        Return value is either a file object, or None (indicating an
        error).  In either case, the headers are sent, making the
        interface the same as for send_head().

        """
        try:
            list = os.listdir(path)
        except os.error:
            self.send_error(404, "No permission to list directory")
            return None
        enc = sys.getfilesystemencoding()
        list.sort(key=lambda a: a.lower())
        f = BytesIO()
        displaypath = html.escape(urllib.parse.unquote(self.path))
        f.write(b'<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">')
        f.write(b'<html>\n')
        f.write(('<meta http-equiv="Content-Type" '
                 'content="text/html; charset=%s">' % enc).encode(enc))
        f.write(("<title>Directory listing for %s</title>\n" % displaypath).encode(enc))
        f.write(b'<style type="text/css">\n')
        f.write(b'* {font-family: Helvetica; font-size: 16px; }\n')
        f.write(b'a { text-decoration: none; }\n')
        f.write(b'a:link { text-decoration: none; font-weight: bold; color: #0000ff; }\n')
        f.write(b'a:visited { text-decoration: none; font-weight: bold; color: #0000ff; }\n')
        f.write(b'a:active { text-decoration: none; font-weight: bold; color: #0000ff; }\n')
        f.write(b'a:hover { text-decoration: none; font-weight: bold; color: #ff0000; }\n')
        f.write(b'table {\n  border-collapse: separate;\n}\n')
        f.write(b'th, td {\n  padding:0px 10px;\n}\n')
        f.write(b'</style>\n')
        f.write(("<body>\n<h2>Directory listing for %s</h2>\n" % displaypath).encode(enc))
        f.write(b"<hr>\n")
        f.write(b"<form ENCTYPE=\"multipart/form-data\" method=\"post\">")
        f.write(b"<input name=\"file\" type=\"file\" multiple/>")
        f.write(b"<input type=\"submit\" value=\"upload\"/></form>\n")
        f.write(b"<p><a href=\"/upload.html\" style=\"display: inline-block; padding: 8px 16px; background-color: #007bff; color: white; text-decoration: none; border-radius: 4px; font-weight: normal; margin: 10px 0;\">Upload Large Files (>100MB)</a></p>\n")
        f.write(b"<hr>\n")
        f.write(b'<table>\n')
        f.write(b'<tr><td><img src="data:image/gif;base64,R0lGODlhGAAYAMIAAP///7+/v7u7u1ZWVTc3NwAAAAAAAAAAACH+RFRoaXMgaWNvbiBpcyBpbiB0aGUgcHVibGljIGRvbWFpbi4gMTk5NSBLZXZpbiBIdWdoZXMsIGtldmluaEBlaXQuY29tACH5BAEAAAEALAAAAAAYABgAAANKGLrc/jBKNgIhM4rLcaZWd33KJnJkdaKZuXqTugYFeSpFTVpLnj86oM/n+DWGyCAuyUQymlDiMtrsUavP6xCizUB3NCW4Ny6bJwkAOw==" alt="[PARENTDIR]" width="24" height="24"></td><td><a href="../" >Parent Directory</a></td></tr>\n')
        for name in list:
            dirimage = 'data:image/gif;base64,R0lGODlhGAAYAMIAAP///7+/v7u7u1ZWVTc3NwAAAAAAAAAAACH+RFRoaXMgaWNvbiBpcyBpbiB0aGUgcHVibGljIGRvbWFpbi4gMTk5NSBLZXZpbiBIdWdoZXMsIGtldmluaEBlaXQuY29tACH5BAEAAAEALAAAAAAYABgAAANdGLrc/jAuQaulQwYBuv9cFnFfSYoPWXoq2qgrALsTYN+4QOg6veFAG2FIdMCCNgvBiAxWlq8mUseUBqGMoxWArW1xXYXWGv59b+WxNH1GV9vsNvd9jsMhxLw+70gAADs='
            fullname = os.path.join(path, name)
            displayname = linkname = name
            fsize = fbytes(os.path.getsize(fullname))
            created_date = time.ctime(os.path.getctime(fullname))
            # Append / for directories or @ for symbolic links
            if os.path.isdir(fullname):
                dirimage = 'data:image/png;base64,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'
                # Note: a link to a directory displays with @ and links with /
            f.write(('<tr><td><img src="%s" width="24" height="24"></td><td><a href="%s">%s</a></td><td style="text-align:right; font-weight: bold; color:#FF0000">%s</td><td style="text-align:right; font-weight: bold;">%s</td></tr>\n'
                    % ( dirimage, urllib.parse.quote(linkname), html.escape(displayname) , fsize , created_date )).encode(enc))
        f.write(b"</table><hr>\n</body>\n</html>\n")
        length = f.tell()
        f.seek(0)
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        return f

    def translate_path(self, path):
        """Translate a /-separated PATH to the local filename syntax.

        Components that mean special things to the local file system
        (e.g. drive or directory names) are ignored.  (XXX They should
        probably be diagnosed.)

        """
        # abandon query parameters
        path = path.split('?',1)[0]
        path = path.split('#',1)[0]
        path = posixpath.normpath(urllib.parse.unquote(path))
        words = path.split('/')
        words = [_f for _f in words if _f]
        path = os.getcwd()
        for word in words:
            drive, word = os.path.splitdrive(word)
            head, word = os.path.split(word)
            if word in (os.curdir, os.pardir): continue
            path = os.path.join(path, word)
        return path
 
    def copyfile(self, source, outputfile):
        """Copy all data between two file objects.

        The SOURCE argument is a file object open for reading
        (or anything with a read() method) and the DESTINATION
        argument is a file object open for writing (or
        anything with a write() method).

        The only reason for overriding this would be to change
        the block size or perhaps to replace newlines by CRLF
        -- note however that this the default server uses this
        to copy binary data as well.

        """
        shutil.copyfileobj(source, outputfile)
 
    def guess_type(self, path):
        """Guess the type of a file.

        Argument is a PATH (a filename).

        Return value is a string of the form type/subtype,
        usable for a MIME Content-type header.

        The default implementation looks the file's extension
        up in the table self.extensions_map, using application/octet-stream
        as a default; however it would be permissible (if
        slow) to look inside the data to make a better guess.

        """
 
        base, ext = posixpath.splitext(path)
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        ext = ext.lower()
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        else:
            return self.extensions_map['']
 
    if not mimetypes.inited:
        mimetypes.init() # try to read system mime.types
    extensions_map = mimetypes.types_map.copy()
    extensions_map.update({
        '': 'application/octet-stream', # Default
        '.py': 'text/plain',
        '.c': 'text/plain',
        '.h': 'text/plain',
        })
 
    def handle_chunk_upload(self):
        """Handle individual chunk uploads for large files."""
        try:
            # Parse query parameters
            from urllib.parse import parse_qs, urlparse
            parsed_url = urlparse(self.path)
            params = parse_qs(parsed_url.query)
            
            chunk_id = params.get('chunk', [None])[0]
            total_chunks = params.get('total', [None])[0]
            filename = params.get('filename', [None])[0]
            
            if not all([chunk_id, total_chunks, filename]):
                return (False, "Missing required parameters: chunk, total, filename")
            
            chunk_id = int(chunk_id)
            total_chunks = int(total_chunks)
            
            # Create chunks directory if it doesn't exist
            chunks_dir = os.path.join(os.getcwd(), '.chunks')
            os.makedirs(chunks_dir, exist_ok=True)
            
            # Save chunk with unique identifier
            chunk_filename = f"{filename}.chunk_{chunk_id:04d}"
            chunk_path = os.path.join(chunks_dir, chunk_filename)
            
            # Read the chunk data
            content_length = int(self.headers.get('content-length', 0))
            chunk_data = self.rfile.read(content_length)
            
            with open(chunk_path, 'wb') as f:
                f.write(chunk_data)
            
            print(f"Received chunk {chunk_id + 1}/{total_chunks} for {filename} ({fbytes(len(chunk_data))})")
            
            return (True, f"Chunk {chunk_id + 1}/{total_chunks} uploaded successfully")
            
        except Exception as e:
            return (False, f"Error uploading chunk: {str(e)}")

    def handle_finalize_upload(self):
        """Reassemble chunks into final file."""
        try:
            # Parse query parameters
            from urllib.parse import parse_qs, urlparse
            parsed_url = urlparse(self.path)
            params = parse_qs(parsed_url.query)
            
            filename = params.get('filename', [None])[0]
            total_chunks = params.get('total', [None])[0]
            
            if not all([filename, total_chunks]):
                return (False, "Missing required parameters: filename, total")
            
            total_chunks = int(total_chunks)
            chunks_dir = os.path.join(os.getcwd(), '.chunks')
            
            # Check if all chunks exist
            missing_chunks = []
            for i in range(total_chunks):
                chunk_filename = f"{filename}.chunk_{i:04d}"
                chunk_path = os.path.join(chunks_dir, chunk_filename)
                if not os.path.exists(chunk_path):
                    missing_chunks.append(i)
            
            if missing_chunks:
                return (False, f"Missing chunks: {missing_chunks}")
            
            # Reassemble file
            final_path = os.path.join(os.getcwd(), filename)
            total_size = 0
            
            with open(final_path, 'wb') as final_file:
                for i in range(total_chunks):
                    chunk_filename = f"{filename}.chunk_{i:04d}"
                    chunk_path = os.path.join(chunks_dir, chunk_filename)
                    
                    with open(chunk_path, 'rb') as chunk_file:
                        chunk_data = chunk_file.read()
                        final_file.write(chunk_data)
                        total_size += len(chunk_data)
                    
                    # Clean up chunk file
                    os.remove(chunk_path)
            
            print(f"Successfully assembled {filename} ({fbytes(total_size)})")
            
            return (True, f"File {filename} uploaded successfully ({fbytes(total_size)})")
            
        except Exception as e:
            return (False, f"Error finalizing upload: {str(e)}")
 
parser = argparse.ArgumentParser()
parser.add_argument('--bind', '-b', default='', metavar='ADDRESS',
                        help='Specify alternate bind address '
                             '[default: all interfaces]')
parser.add_argument('port', action='store',
                        default=8000, type=int,
                        nargs='?',
                        help='Specify alternate port [default: 8000]')
args = parser.parse_args()

PORT = args.port
BIND = args.bind
HOST = BIND

if HOST == '':
	HOST = 'localhost'

Handler = SimpleHTTPRequestHandler

with socketserver.TCPServer((BIND, PORT), Handler) as httpd:
	serve_message = "Serving HTTP on {host} port {port} (http://{host}:{port}/) ..."
	print(serve_message.format(host=HOST, port=PORT))
	httpd.serve_forever()
