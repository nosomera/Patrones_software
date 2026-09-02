class GestorMedicinas:
    _instancia = None

    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            cls._instancia.medicinas = []

        return cls._instancia

    def agregar_medicina(self, medicina):
        self.medicinas.append(medicina)

    def obtener_medicinas(self):
        return self.medicinas