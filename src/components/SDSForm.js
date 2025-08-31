import React, { useState } from 'react';
// Removed unused axios import

import { FaExclamationTriangle } from 'react-icons/fa';

export default function SDSForm() {
  const [smiles, setSmiles] = useState('');
  const [sds, setSds] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Prefer local backend during development; override via REACT_APP_API_BASE
  const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:5000"; // Flask backend

  const handleSubmit = async () => {
    setLoading(true);
    setError('');
    try {
      // ✅ FIXED: Use /api/sds instead of /sds
      const res = await fetch(`${API_BASE}/api/sds?smiles=${encodeURIComponent(smiles)}`);

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || 'Failed to fetch SDS');
      }

      const data = await res.json();
      setSds(data);
    } catch (err) {
      setError(err.message);
      setSds(null);
    } finally {
      setLoading(false);
    }
  };

  const downloadPDF = () => {
    if (!smiles.trim()) return;
    window.open(`${API_BASE}/api/sds/pdf?smiles=${encodeURIComponent(smiles)}`, '_blank');
  };

  const downloadDOCX = () => {
    if (!smiles.trim()) return;
    window.open(`${API_BASE}/api/sds/docx?smiles=${encodeURIComponent(smiles)}`, '_blank');
  };

  const downloadJSON = async () => {
    if (!smiles.trim()) return;
    try {
      // ✅ FIXED: Use /api/sds/json
      const response = await fetch(`${API_BASE}/api/sds/json?smiles=${encodeURIComponent(smiles)}`);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `sds_report.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError("Download failed.");
    }
  };

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold text-center mb-6 text-blue-600">🧪 SDS Generator</h1>
      
      <div className="flex gap-2 mb-6">
        <input
          type="text"
          value={smiles}
          onChange={(e) => setSmiles(e.target.value)}
          placeholder="Enter SMILES (e.g., CCO)"
          className="flex-grow p-3 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          onClick={handleSubmit}
          disabled={loading}
          className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Generating..." : "Generate SDS"}
        </button>
      </div>

      {error && <p className="text-red-500 mb-4">{error}</p>}

      {sds && (
        <div>
          <div className="flex gap-3 mb-6">
            <button onClick={downloadPDF} className="flex-1 bg-green-600 text-white py-2 rounded hover:bg-green-700">
              📄 PDF
            </button>
            <button onClick={downloadDOCX} className="flex-1 bg-indigo-600 text-white py-2 rounded hover:bg-indigo-700">
              📄 DOCX
            </button>
            <button onClick={downloadJSON} className="flex-1 bg-gray-600 text-white py-2 rounded hover:bg-gray-700">
              📥 JSON
            </button>
          </div>

          <SDSDisplay sds={sds} />
        </div>
      )}
    </div>
  );
}


function SDSDisplay({ sds }) {
  return (
    <div className="bg-gray-100 p-6">
      {/* Header */}
      <h1 className="text-3xl font-bold text-center mb-6 text-blue-600">🧪 Safety Data Sheet (SDS)</h1>
      <p className="text-center text-gray-500">Generated on: {new Date().toLocaleString()}</p>

      {/* Section Loop */}
      {Object.keys(sds).map((sectionKey) => {
        const section = sds[sectionKey];
        return (
          <div key={sectionKey} className="my-6 bg-white rounded-lg shadow-md p-4">
            {/* Section Title */}
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold">{section.title}</h2>
              {/* Warning Icon (if applicable) */}
              {sectionKey === "Section3" && (
                <span className="text-red-500 text-2xl">
                  <FaExclamationTriangle />
                </span>
              )}
            </div>

            {/* Section Content */}
            <table className="w-full border-collapse border border-gray-300">
              <thead>
                <tr>
                  <th className="border border-gray-300 p-2 bg-green-500 text-white">Property</th>
                  <th className="border border-gray-300 p-2 bg-green-500 text-white">Value</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(section.data).map(([key, value], index) => (
                  <tr key={index} className="border-b border-gray-300">
                    <td className="border border-gray-300 p-2">{key}</td>
                    <td className="border border-gray-300 p-2">
                      {Array.isArray(value)
                        ? value.join(", ")
                        : value || "Not available"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
    </div>
  );
}

