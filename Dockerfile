FROM python:3.14-slim

USER root
WORKDIR /app

RUN pip install poetry

COPY payout_gateway payout_gateway
COPY --chown=user scripts/* .
COPY README.md .

COPY poetry.lock pyproject.toml ./
RUN poetry install --without dev

RUN chmod u+x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
CMD ["payout_gateway", "run"]
