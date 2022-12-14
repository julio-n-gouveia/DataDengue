from ast import Return
from ntpath import join
import re
import apache_beam as beam
from apache_beam.io import ReadFromText
from apache_beam.io.textio import WriteToText
from apache_beam.options.pipeline_options import PipelineOptions

pipeline_options = PipelineOptions(argc=None)
pipeline = beam.Pipeline(options=pipeline_options)

# Metodos da extração dos casos de Dengue
colunas_dengue = [
                'id',
                'data_iniSE',
                'casos',
                'ibge_code',
                'cidade',
                'uf',
                'cep',
                'latitude',
                'longitude']

def lista_dicionario (elemento, colunas):
    return dict(zip(colunas, elemento))

def lista (elemento, delimitador="|"):
    return elemento.split(delimitador)

def trata_data (elemento):
    elemento['ano_mes'] = '-'.join(elemento['data_iniSE'].split('-')[:2])
    return elemento

def chave_uf(elemento):
    chave = elemento['uf']
    return (chave, elemento)

def casos_dengue(elemento):
    uf, registros = elemento
    for registro in registros:
        if bool(re.search(r'\d', registro['casos'])):
            yield (f"{uf}-{registro['ano_mes']}", float(registro['casos']))
        else:
            yield (f"{uf}-{registro['ano_mes']}", 0.0)
            
       
#Metodos para o volume de chuvas
def chave_uf_ano_mes(elemento):
    data, mm, uf = elemento
    ano_mes = '-'.join(data.split('-')[:2])
    chave = f"{uf}-{ano_mes}"
    if float(mm) < 0:
        mm = 0.0
    else:
        mm = float(mm)
    return chave, mm

def arredonda(elemento):
    chave, mm = elemento
    return (chave, round(mm, 1))

# Metodos para os resultados
   
def filtro_campos_vazios(elemento):
    chave, dados = elemento
    if all([
    dados['chuvas'],
    dados['dengue']
    ]):
        return True
    return False

def descompactador(elemento):
    chave, dados = elemento
    chuva = dados['chuvas'][0]
    dengue = dados['dengue'][0]
    uf, ano, mes = chave.split('-')
    return uf, ano, mes, str(chuva), str(dengue)

def preparar_csv(elemento, delimitador=';'):
    return f"{delimitador}".join(elemento)

# Execução dos metodos
dengue = (
    pipeline
    |"Leitura do dataset de dengue" >>
    ReadFromText('casos_dengue.txt', skip_header_lines=1)
    | "De texto para lista" >> beam.Map(lista)
    | "De lista para dicionário" >> beam.Map(lista_dicionario, colunas_dengue)
    | "Criar campo ano_mes" >> beam.Map(trata_data)
    | "Criar chave pelo estado" >> beam.Map(chave_uf)
    | "Agrupar pelo estado" >> beam.GroupByKey()
    |"Descompactar casos de Dengue" >> beam.FlatMap(casos_dengue)
    | "Somar casos de dengue" >> beam.CombinePerKey(sum)
   )

chuvas = (
    pipeline
    |"Leitura do dataset de chuvas" >>
    ReadFromText('chuvas.csv', skip_header_lines=1)
    | "De texto para chuva" >> beam.Map(lista, delimitador=",")
    | "criando chave UF-ANO-MES" >> beam.Map(chave_uf_ano_mes)
    | "Somar total de chuvas pela chave" >> beam.CombinePerKey(sum)
    | "Resultados de chuvas, arredondados" >> beam.Map(arredonda)
)

resultado = (
    ({'chuvas': chuvas, 'dengue': dengue})
    | "Mesclar pcols" >> beam.CoGroupByKey()
    | "Filtrar dados vazios" >> beam.Filter(filtro_campos_vazios)
    | "Descompactar elementos" >> beam.Map(descompactador)
    |"Prepparar csv" >> beam.Map(preparar_csv)
)

header = 'UF;ANO;MES;CHUVA;DENGUE'

resultado | 'Criar arquivo CSV' >> WriteToText('resultado', file_name_suffix='.csv', header=header)

pipeline.run()
