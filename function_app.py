import json
import azure.functions as func
import logging
from azure.functions.decorators.core import DataType
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.statespace.sarimax import SARIMAX

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

@app.route(route="http_trigger/{equipmentId}")
@app.sql_input(arg_name="reservations",
                        command_text="SELECT YEAR(CreatedAt) AS year, MONTH(CreatedAt) AS month, COUNT(*) AS count FROM dbo.itemReservations WHERE EquipmentId = @EquipmentId GROUP BY YEAR(CreatedAt), MONTH(CreatedAt) ORDER BY year, month;",
                        command_type="Text",
                        parameters="@EquipmentId={equipmentId}",
                        connection_string_setting="SqlConnectionString")
def http_trigger(req: func.HttpRequest, reservations: func.SqlRowList) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    rows = list(map(lambda r: json.loads(r.to_json()), reservations))

    # If rows is empty, return an empty response
    if not rows:
        return func.HttpResponse(
            "No data found for the given EquipmentId",
            status_code=404
        )

    # Convert the data to a DataFrame
    df = pd.DataFrame(rows)

    # Create a datetime index for the data
    df['date'] = pd.to_datetime(df[['year', 'month']].assign(day=1))
    df.set_index('date', inplace=True)

    # Extract the 'count' column as the time series data
    ts_data = df['count']

    # Fit the SARIMA model
    # (p, d, q) are the ARIMA parameters and (P, D, Q, s) are the seasonal parameters
    model = SARIMAX(ts_data, order=(1, 1, 1), seasonal_order=(1, 1, 1, 12))
    sarima_model = model.fit(disp=False)

    # Forecast the next few months (e.g., 6 months)
    forecast_steps = 6
    forecast = sarima_model.forecast(steps=forecast_steps)

    # Get the last date from the existing data
    last_date = df.index[-1]
    
    # Prepare the forecast output in year, month, count format
    forecast_output = []
    
    for i, count in enumerate(forecast):
        # Calculate the next year and month
        next_date = last_date + pd.DateOffset(months=i+1)
        forecast_output.append({
            "year": next_date.year,
            "month": next_date.month,
            "count": round(count)  # Round the forecasted count to integer
        })
	
	# print the forecast
    logging.info("Forecasted values for EquipmentId: " + req.route_params['equipmentId'] + " are: " + str(forecast.to_list()))

    # Return the results
    return func.HttpResponse(
        json.dumps(forecast_output),
        status_code=200,
        mimetype="application/json"
    )
