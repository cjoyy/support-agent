from __future__ import annotations


schemas = [
    {
        "name": "search_knowledge_base",
        "description": (
            "Gunakan untuk pertanyaan support umum yang kemungkinan jawabannya ada di FAQ/knowledge base, "
            "seperti refund, shipping, login, akun, billing, atau kebijakan layanan. Jangan dipakai untuk "
            "status order spesifik atau saat user jelas meminta manusia."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Pertanyaan pengguna yang perlu dicari di knowledge base.",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "check_order_status",
        "description": (
            "Gunakan hanya jika user menanyakan status order yang spesifik dan menyebutkan order ID. "
            "Jangan dipakai untuk pertanyaan kebijakan atau FAQ umum karena tool ini hanya untuk lookup order."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "Order ID yang ingin dicek statusnya.",
                }
            },
            "required": ["order_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_ticket",
        "description": (
            "Gunakan ketika masalah perlu ditracking sebagai tiket, misalnya setelah knowledge base tidak cukup, "
            "ada follow-up manual yang diperlukan, atau issue butuh ditindaklanjuti tim support. Jangan dipakai "
            "untuk pertanyaan yang bisa diselesaikan langsung dengan knowledge base atau lookup order."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "issue": {
                    "type": "string",
                    "description": "Ringkasan masalah customer yang perlu dibuatkan ticket.",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Prioritas ticket berdasarkan urgensi issue.",
                },
            },
            "required": ["issue", "priority"],
            "additionalProperties": False,
        },
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Gunakan jika user secara eksplisit meminta human, jika jawaban tidak yakin, atau jika hasil pencarian "
            "knowledge base maupun order lookup tidak cukup untuk menjawab dengan aman. Tool ini untuk handoff ke "
            "agent manusia, bukan untuk menjawab masalah sendiri."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Alasan kenapa percakapan perlu diteruskan ke manusia.",
                }
            },
            "required": ["reason"],
            "additionalProperties": False,
        },
    },
]
